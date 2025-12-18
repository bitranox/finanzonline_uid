SHELL := /bin/bash

PYTHON ?= python3
SCRIPTS ?= $(PYTHON) -m scripts

.PHONY: help install dev test run clean build push release coverage version-current bump bump-patch bump-minor bump-major dependencies dependencies-update menu i18n-compile

help:
	$(SCRIPTS) help

install:
	$(SCRIPTS) install

dev:
	$(SCRIPTS) dev

test:
	$(SCRIPTS) test

run:
	$(SCRIPTS) run

version-current:
	$(SCRIPTS) version-current

bump:
	$(SCRIPTS) bump

bump-patch:
	$(SCRIPTS) bump-patch

bump-minor:
	$(SCRIPTS) bump-minor

bump-major:
	$(SCRIPTS) bump-major

clean:
	$(SCRIPTS) clean

coverage:
	$(SCRIPTS) coverage

push:
	$(SCRIPTS) push

build:
	$(SCRIPTS) build

release:
	$(SCRIPTS) release

dependencies:
	$(SCRIPTS) dependencies

dependencies-update:
	$(SCRIPTS) dependencies-update

menu:
	$(SCRIPTS) menu

i18n-compile:  ## Compile .po files to .mo files for all languages
	@for lang in de es fr ru; do \
		msgfmt -o src/uid_check_austria/locales/$$lang/LC_MESSAGES/messages.mo \
		       src/uid_check_austria/locales/$$lang/LC_MESSAGES/messages.po 2>/dev/null || \
		$(PYTHON) -c "from tools.msgfmt import make; make('src/uid_check_austria/locales/$$lang/LC_MESSAGES/messages.po', 'src/uid_check_austria/locales/$$lang/LC_MESSAGES/messages.mo')" 2>/dev/null || \
		echo "Compiled $$lang"; \
	done
