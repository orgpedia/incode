.PHONY: all fetch_list fetch_acts_mah

all: fetch_list fetch_acts_mah

fetch_list:
	python import/src/fetch_list.py import/src/state.json

fetch_acts_mah:
	python import/src/fetch_acts.py import/website/Maharashtra/act_infos.json

help:
	@echo "make fetch_list        # Run fetch_list.py to fetch the list of acts"
	@echo "make fetch_acts_mah    # Run fetch_acts.py for Maharashtra acts"
	@echo "make all               # Run both commands in order"
