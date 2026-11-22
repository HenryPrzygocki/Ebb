# Fork #14.
#   make test                        every test, headless and isolated (tools/test.sh)
#   make test ARGS='-k credits'      arguments for pytest
.PHONY: test
test:
	@tools/test.sh $(ARGS)
