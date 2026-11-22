//! Fork: gapless playback.
//!
//! Upstream ended every track the same way:
//!   1. drain the output;
//!   2. emit EOS;
//!   3. let Python load the next track, which tore down the decode worker, closed the output,
//!      fetched and probed the new stream, and reopened the output.
//!
//! That left a gap of a few hundred milliseconds between tracks. It breaks albums meant to
//! play as one piece, such as The Dark Side of the Moon, live albums and DJ mixes.
//!
//! Now, `PREPARE_LEAD_S` before the decoder reaches the end of a track:
//!   1. the worker emits `native-transport about-to-finish uri=<current>`;
//!   2. the app answers with the next track (`NativeTransportCommand::SetNext`);
//!   3. a helper thread here opens and probes it.
//!
//! At end of stream the decode worker takes it. It keeps decoding into the same output session
//! and processor chain, so the next track's first sample follows this track's last sample.
//! The worker then emits `native-transport gapless-advance ... uri=<next>`, and the app updates
//! its UI without reloading the engine.
//!
//! Only a next track with the same sample rate, channel count and bit depth continues this way.
//! That covers albums, which are mastered in one format. In every other case the track ends as
//! before:
//!   - a different format;
//!   - an open that failed;
//!   - an open not ready within `READY_WAIT`.

use super::controller::{
    format_mpd_source_summary, open_source_as_media_source_stream, read_locator_to_string,
    source_probe_hint, NativeTransportLoadRequest, NativeTransportSnapshot,
};
use super::source::{inspect_mpd_manifest, MpdManifestInfo, NativeTransportSource};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use symphonia::core::codecs::{Decoder, DecoderOptions, CODEC_TYPE_NULL};
use symphonia::core::formats::{FormatOptions, FormatReader, Track};
use symphonia::core::meta::MetadataOptions;
use symphonia::core::probe::Hint;

/// How long before the end of a track the app is asked for the next one.
pub(crate) const PREPARE_LEAD_S: f64 = 20.0;
/// How long the end of a track waits for a next track that is still opening.
pub(crate) const READY_WAIT: Duration = Duration::from_secs(8);

pub(crate) struct PreparedNext {
    pub request: NativeTransportLoadRequest,
    pub format: Box<dyn FormatReader>,
    pub decoder: Box<dyn Decoder>,
    pub track: Track,
    pub mpd_info: Option<MpdManifestInfo>,
    /// Stops this stream's download thread.
    pub stop: Arc<AtomicBool>,
}

struct Pending {
    serial: u64,
    stop: Arc<AtomicBool>,
    result: Option<Result<PreparedNext, String>>,
}

#[derive(Default)]
struct Inner {
    serial: u64,
    pending: Option<Pending>,
    advanced: Option<NativeTransportSource>,
}

/// The queued next track. The controller sets it; whichever decode worker reaches end of
/// stream takes it. It outlives workers, so it survives pause, resume and seek.
#[derive(Clone, Default)]
pub(crate) struct GaplessSlot(Arc<Mutex<Inner>>);

impl GaplessSlot {
    /// Queue `request` as the next track, replacing any queued one, and start opening it.
    /// `None` only drops the queued track.
    pub fn set(&self, request: Option<NativeTransportLoadRequest>) {
        let Ok(mut inner) = self.0.lock() else {
            return;
        };
        if let Some(old) = inner.pending.take() {
            old.stop.store(true, Ordering::Release);
        }
        let Some(request) = request else {
            return;
        };
        inner.serial = inner.serial.wrapping_add(1);
        let serial = inner.serial;
        let stop = Arc::new(AtomicBool::new(false));
        inner.pending = Some(Pending {
            serial,
            stop: Arc::clone(&stop),
            result: None,
        });
        drop(inner);
        let slot = self.clone();
        let spawned = thread::Builder::new()
            .name("native-transport-gapless-open".to_string())
            .spawn(move || {
                let started = Instant::now();
                let result = prepare(request, &stop);
                match &result {
                    Ok(next) => eprintln!(
                        "native-transport: gapless: next track ready in {} ms ({})",
                        started.elapsed().as_millis(),
                        next.request.source.locator(),
                    ),
                    Err(err) => eprintln!("native-transport: gapless: next track failed to open: {err}"),
                }
                let Ok(mut inner) = slot.0.lock() else {
                    return;
                };
                match inner.pending.as_mut() {
                    Some(pending) if pending.serial == serial => pending.result = Some(result),
                    // Replaced or dropped while it opened: let it go.
                    _ => stop.store(true, Ordering::Release),
                }
            });
        if let Err(err) = spawned {
            if let Ok(mut inner) = self.0.lock() {
                if let Some(pending) = inner.pending.as_mut().filter(|p| p.serial == serial) {
                    pending.result = Some(Err(format!("could not start the opener: {err}")));
                }
            }
        }
    }

    /// Drop the queued track, and forget an advance the controller hasn't picked up yet
    /// (a new Load or a Stop supersedes it).
    pub fn clear(&self) {
        self.set(None);
        let _ = self.take_advanced();
    }

    pub fn is_queued(&self) -> bool {
        self.0.lock().map(|inner| inner.pending.is_some()).unwrap_or(false)
    }

    /// At end of stream, take the queued next track, waiting up to `wait` while it opens.
    ///
    /// - `None`: nothing is queued, or `stop` was raised. A raised stop leaves the queued
    ///   track for the worker that resumes after a pause.
    /// - `Some(Err)`: it failed to open, or wasn't ready in time; it is dropped.
    pub fn take(&self, stop: &AtomicBool, wait: Duration) -> Option<Result<PreparedNext, String>> {
        let deadline = Instant::now() + wait;
        loop {
            {
                let Ok(mut inner) = self.0.lock() else {
                    return None;
                };
                let ready = match inner.pending.as_ref() {
                    None => return None,
                    Some(pending) => pending.result.is_some(),
                };
                if ready {
                    return inner.pending.take().and_then(|pending| pending.result);
                }
                if stop.load(Ordering::Acquire) {
                    return None;
                }
                if Instant::now() >= deadline {
                    if let Some(pending) = inner.pending.take() {
                        pending.stop.store(true, Ordering::Release);
                    }
                    return Some(Err(format!("not ready after {} s", wait.as_secs())));
                }
            }
            thread::sleep(Duration::from_millis(5));
        }
    }

    /// The worker moved on to the queued track; the controller adopts it as its current
    /// source (resume and seek reopen the current source).
    pub fn note_advanced(&self, source: NativeTransportSource) {
        if let Ok(mut inner) = self.0.lock() {
            inner.advanced = Some(source);
        }
    }

    pub fn take_advanced(&self) -> Option<NativeTransportSource> {
        self.0.lock().ok().and_then(|mut inner| inner.advanced.take())
    }
}

fn prepare(request: NativeTransportLoadRequest, stop: &Arc<AtomicBool>) -> Result<PreparedNext, String> {
    let (mss, _) = open_source_as_media_source_stream(&request.source, stop, None)?;
    let mut hint = Hint::new();
    if let Some(extension) = source_probe_hint(&request.source) {
        hint.with_extension(extension);
    }
    let probe = symphonia::default::get_probe()
        .format(&hint, mss, &FormatOptions::default(), &MetadataOptions::default())
        .map_err(|e| format!("probe failed: {e}"))?;
    let format = probe.format;
    let track = format
        .default_track()
        .filter(|track| track.codec_params.codec != CODEC_TYPE_NULL)
        .cloned()
        .ok_or_else(|| "no decodable audio track".to_string())?;
    let decoder = symphonia::default::get_codecs()
        .make(&track.codec_params, &DecoderOptions::default())
        .map_err(|e| format!("decoder init failed: {e}"))?;
    let mpd_info = match &request.source {
        NativeTransportSource::TidalMpd { manifest_uri, .. } => read_locator_to_string(manifest_uri)
            .ok()
            .and_then(|xml| inspect_mpd_manifest(&xml).ok()),
        _ => None,
    };
    Ok(PreparedNext {
        request,
        format,
        decoder,
        track,
        mpd_info,
        stop: Arc::clone(stop),
    })
}

/// Why `next` can't continue in the output opened for `current`; None if it can.
pub(crate) fn incompatibility(current: &Track, next: &Track) -> Option<String> {
    let (a, b) = (&current.codec_params, &next.codec_params);
    if a.sample_rate.is_none() || a.sample_rate != b.sample_rate {
        return Some(format!("sample rate {:?} -> {:?}", a.sample_rate, b.sample_rate));
    }
    let channels = (a.channels.map(|c| c.count()), b.channels.map(|c| c.count()));
    if channels.0 != channels.1 {
        return Some(format!("channels {:?} -> {:?}", channels.0, channels.1));
    }
    if a.bits_per_sample != b.bits_per_sample {
        return Some(format!("bit depth {:?} -> {:?}", a.bits_per_sample, b.bits_per_sample));
    }
    None
}

/// A track's duration from its probe, else from its DASH manifest.
pub(crate) fn track_duration_s(track: &Track, mpd_info: Option<&MpdManifestInfo>) -> Option<f64> {
    track
        .codec_params
        .n_frames
        .filter(|n| *n > 0)
        .and_then(|n| {
            let rate = track.codec_params.sample_rate.unwrap_or(0) as f64;
            (rate > 0.0).then(|| n as f64 / rate)
        })
        .or_else(|| mpd_info.and_then(|info| info.total_duration_s()))
}

/// Time to ask for the next track: the decoder is `position_s` into a track of `duration_s`.
pub(crate) fn due(position_s: f64, duration_s: Option<f64>) -> bool {
    duration_s.map_or(false, |d| d > 0.0 && position_s + PREPARE_LEAD_S >= d)
}

/// The snapshot now describes the next track, whose position starts at 0.
///
/// `seek_offset_s` is chosen so that the position the transport reports starts at 0:
/// - the decode-clock fallback: position is seek_offset + decoded_frame_count / rate, so the
///   offset is 0;
/// - USB hardware clock: position is seek_offset + elapsed since the session opened, so the
///   offset is minus the elapsed time so far.
pub(crate) fn adopt_in_snapshot(
    snapshot: &Arc<Mutex<NativeTransportSnapshot>>,
    generation: u64,
    request: &NativeTransportLoadRequest,
    track: &Track,
    mpd_info: Option<&MpdManifestInfo>,
    duration_s: Option<f64>,
    seek_offset_s: f64,
) {
    let plan = request.source.plan();
    let Ok(mut state) = snapshot.lock() else {
        return;
    };
    if state.generation != generation {
        return;
    }
    state.current_track_id = Some(request.source.track().track_id.clone());
    state.current_title = Some(request.source.track().title.clone());
    state.source_kind = Some(plan.source_kind);
    state.decoder = Some(plan.decoder);
    state.supports_seek = plan.supports_seek;
    state.duration_s = duration_s;
    state.source_locator = Some(request.source.locator().to_string());
    state.bits_per_sample = track.codec_params.bits_per_sample;
    state.first_packet_frames = None;
    state.decoded_slab_count = 0;
    state.decoded_frame_count = 0;
    state.decoded_byte_count = 0;
    state.decode_completed = false;
    state.source_summary = mpd_info.map(format_mpd_source_summary);
    state.last_error = None;
    state.seek_offset_s = seek_offset_s;
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::source::TidalTrackContext;
    use symphonia::core::audio::Channels;
    use symphonia::core::codecs::CodecParameters;

    fn track(rate: u32, channels: Channels, bits: Option<u32>) -> Track {
        let mut params = CodecParameters::new();
        params.with_sample_rate(rate).with_channels(channels);
        if let Some(bits) = bits {
            params.with_bits_per_sample(bits);
        }
        Track::new(0, params)
    }

    #[test]
    fn same_format_continues_anything_else_reopens() {
        let stereo = Channels::FRONT_LEFT | Channels::FRONT_RIGHT;
        let a = track(96_000, stereo, Some(24));
        assert_eq!(incompatibility(&a, &track(96_000, stereo, Some(24))), None);
        assert!(incompatibility(&a, &track(44_100, stereo, Some(24))).unwrap().contains("sample rate"));
        assert!(incompatibility(&a, &track(96_000, stereo, Some(16))).unwrap().contains("bit depth"));
        assert!(incompatibility(&a, &track(96_000, Channels::FRONT_LEFT, Some(24))).unwrap().contains("channels"));
        // AAC (no bit depth) follows AAC, but not FLAC.
        let aac = track(44_100, stereo, None);
        assert_eq!(incompatibility(&aac, &track(44_100, stereo, None)), None);
        assert!(incompatibility(&aac, &track(44_100, stereo, Some(16))).is_some());
    }

    #[test]
    fn asks_for_the_next_track_shortly_before_the_end() {
        assert!(!due(100.0, Some(200.0)));
        assert!(due(180.0, Some(200.0)));
        assert!(due(0.0, Some(12.0)), "a track shorter than the lead asks at once");
        assert!(!due(500.0, None), "unknown duration: the track just ends, as before");
    }

    #[test]
    fn a_next_track_that_fails_to_open_is_reported_and_dropped() {
        let slot = GaplessSlot::default();
        slot.set(Some(NativeTransportLoadRequest {
            source: NativeTransportSource::TidalMpd {
                manifest_uri: "/nonexistent/ebb-gapless-test.mpd".to_string(),
                track: TidalTrackContext {
                    track_id: "2".to_string(),
                    title: "B".to_string(),
                    quality_label: "LOSSLESS".to_string(),
                },
            },
            target_driver: "test".to_string(),
            bit_perfect: true,
            output_target: None,
            dsp_config: None,
        }));
        assert!(slot.is_queued());
        let stop = AtomicBool::new(false);
        assert!(matches!(slot.take(&stop, Duration::from_secs(5)), Some(Err(_))));
        assert!(!slot.is_queued());
        assert!(slot.take(&stop, Duration::from_millis(10)).is_none(), "nothing queued any more");
    }

    #[test]
    fn clearing_drops_the_queued_track_and_a_pending_advance() {
        let slot = GaplessSlot::default();
        let source = NativeTransportSource::TidalMpd {
            manifest_uri: "/nonexistent/ebb-gapless-test.mpd".to_string(),
            track: TidalTrackContext {
                track_id: "2".to_string(),
                title: "B".to_string(),
                quality_label: "LOSSLESS".to_string(),
            },
        };
        slot.note_advanced(source.clone());
        slot.set(Some(NativeTransportLoadRequest {
            source,
            target_driver: "test".to_string(),
            bit_perfect: true,
            output_target: None,
            dsp_config: None,
        }));
        slot.clear();
        assert!(!slot.is_queued());
        assert!(slot.take_advanced().is_none());
    }
}
