"""Fork: the small dialogs, with one look.

Confirmations, messages, name prompts and pickers were hand-built Gtk.Dialog windows whose
title lived in the window's title bar. A compositor that draws none (niri) showed them as
untitled boxes: "Delete 'X' permanently?" in 201 x 90 px with a plain Delete button, a
playlist picker with no heading. These are Adw.AlertDialogs, as "Get Lossless" already was:
inside the window, with a heading, Escape for cancel and Enter for the default response.
"""
from gi.repository import Adw, Gtk

CANCEL = "cancel"
CONFIRM = "confirm"


def _alert(heading, body):
    return Adw.AlertDialog(heading=str(heading or ""), body=str(body or ""))


def present(app, dialog):
    """Show an in-window dialog. From the mini player the full window comes back first: its
    strip is far smaller than any dialog."""
    if getattr(app, "is_mini_mode", False) and callable(getattr(app, "toggle_mini_mode", None)):
        try:
            app.toggle_mini_mode(None)
        except Exception:
            pass
    dialog.present(app.win)


def message(app, heading, body, on_close=None, ok_label="OK"):
    """Something to read. on_close runs however it is dismissed."""
    dialog = _alert(heading, body)
    dialog.add_response(CONFIRM, ok_label)
    dialog.set_default_response(CONFIRM)
    dialog.set_close_response(CONFIRM)
    if on_close is not None:
        dialog.connect("response", lambda _d, _response: on_close())
    present(app, dialog)
    return dialog


def confirm(app, heading, body, confirm_label, on_confirm, destructive=False, cancel_label="Cancel"):
    """A yes/no question. A destructive answer is styled as one and is never the default:
    Enter cancels, so deleting takes a deliberate click."""
    dialog = _alert(heading, body)
    dialog.add_response(CANCEL, cancel_label)
    dialog.add_response(CONFIRM, confirm_label)
    dialog.set_response_appearance(
        CONFIRM, Adw.ResponseAppearance.DESTRUCTIVE if destructive else Adw.ResponseAppearance.SUGGESTED
    )
    dialog.set_default_response(CANCEL if destructive else CONFIRM)
    dialog.set_close_response(CANCEL)
    dialog.connect("response", lambda _d, response: on_confirm() if response == CONFIRM else None)
    present(app, dialog)
    return dialog


def prompt_text(app, heading, body, initial, on_submit, placeholder=None, save_label="Save"):
    """One line of text. on_submit gets it stripped, even when empty: the callers decide."""
    dialog = _alert(heading, body)
    entry = Gtk.Entry(text=str(initial or ""), activates_default=True)
    if placeholder:
        entry.set_placeholder_text(str(placeholder))
    dialog.set_extra_child(entry)
    dialog.add_response(CANCEL, "Cancel")
    dialog.add_response(CONFIRM, str(save_label or "Save"))
    dialog.set_response_appearance(CONFIRM, Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response(CONFIRM)
    dialog.set_close_response(CANCEL)
    dialog.connect(
        "response", lambda _d, response: on_submit(entry.get_text().strip()) if response == CONFIRM else None
    )
    dialog.set_focus(entry)
    present(app, dialog)
    return dialog


def choose(app, heading, body, labels, confirm_label, on_choose, extra_child=None, extra_responses=()):
    """Pick one of `labels` from a dropdown (type to filter it). on_choose gets the index.

    extra_child goes under the dropdown; extra_responses are (label, callback) buttons between
    Cancel and the confirm button.
    """
    dialog = _alert(heading, body)
    dropdown = Gtk.DropDown(model=Gtk.StringList.new([str(label) for label in labels]))
    # Type to filter: a long list (every playlist of the account) is not a scroll hunt.
    dropdown.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
    dropdown.set_enable_search(len(labels) > 8)
    dropdown.set_selected(0)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.append(dropdown)
    if extra_child is not None:
        box.append(extra_child)
    dialog.set_extra_child(box)
    dialog.add_response(CANCEL, "Cancel")
    callbacks = {}
    for index, (label, callback) in enumerate(extra_responses):
        response_id = f"extra-{index}"
        dialog.add_response(response_id, label)
        callbacks[response_id] = callback
    dialog.add_response(CONFIRM, confirm_label)
    dialog.set_response_appearance(CONFIRM, Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response(CONFIRM)
    dialog.set_close_response(CANCEL)

    def _on_response(_dialog, response):
        if response == CONFIRM:
            index = int(dropdown.get_selected())
            if 0 <= index < len(labels):
                on_choose(index)
        elif response in callbacks:
            callbacks[response]()

    dialog.connect("response", _on_response)
    present(app, dialog)
    return dialog


def close_on_escape(window):
    """A plain window (Adw.Window) does not close on Escape by itself; a dialog should."""
    controller = Gtk.ShortcutController()
    controller.add_shortcut(
        Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("Escape"),
            Gtk.CallbackAction.new(lambda *_args: (window.close(), True)[1]),
        )
    )
    window.add_controller(controller)
