# make data   - download every İETT line and stop (İBB), each line's stop order (İETT), and the minibüs/dolmuş data (İBB)
# make map    - compile the minibüs/dolmuş routes and draw the map (out/istanbul-route-map.svg)
# make images - the overview PNG and the 4×3 full-resolution tiles (needs: cd tools && npm install, and Google Chrome)
IBB := https://api.ibb.gov.tr/iett/UlasimAnaVeri/HatDurakGuzergah.asmx
DATA := https://data.ibb.gov.tr/dataset

data:
	mkdir -p data/lines data/dolmus
	./soap.sh $(IBB) GetHat_json "<HatKodu></HatKodu>" > data/hat.xml && sleep 10
	./soap.sh $(IBB) GetDurak_json "<DurakKodu></DurakKodu>" > data/durak.xml
	python3 unwrap.py data/hat.xml data/hat.json
	python3 unwrap.py data/durak.xml data/durak.json
	python3 fetch_orders.py
	cd data/dolmus && curl -sSO $(DATA)/07603812-6e3e-489f-96a0-2da9c3da3193/resource/ac77adc1-11ed-4f3e-a05d-136c9185e510/download/istanbul_taksidolmus_duraklari.geojson \
	  && curl -sSO $(DATA)/fc5f925a-0ee8-4e1f-a4e7-17ab272eac83/resource/1a1fdf1e-60c9-46a4-b169-ca51adcd9d6c/download/istanbul_taksidolmus_guzergahlari.geojson \
	  && curl -sSO $(DATA)/8dad4995-0071-44de-9b14-57288ec1de97/resource/9083216b-7afd-4eae-a242-cf5b09f748f4/download/istanbul_minibus_guzergahlari.geojson \
	  && curl -sSO $(DATA)/8b4391c0-e647-4635-aaf7-5baee24c6e81/resource/0d4fbb9f-cd5f-4005-aa57-6bb76db3fc58/download/istanbul_minibus_duraklari.geojson
	ln -sfn ../durak.json data/dolmus/iett_stops.json

map:
	python3 dolmus_compile.py data/dolmus data/dolmus.json data/dolmus_shapes.json
	mkdir -p out && python3 schematic.py out/istanbul-route-map.svg

images:
	node tools/shot.js out/istanbul-route-map.svg out/istanbul-route-map-overview.png 4842 2925 0 0 0.25
	mkdir -p out/tiles && for r in 0 1 2; do for c in 0 1 2 3; do \
	  node tools/shot.js out/istanbul-route-map.svg out/tiles/tile-r$$((r+1))-c$$((c+1)).png 4843 3901 $$((c*4843)) $$((r*3901)) 1; done; done

.PHONY: data map images
