SHARED_FOLDER=$(HOME)/Dropbox/Public/fg/osm2city/

.PHONY: clean tex-release

tex-release:
	tar czf tex.tar.gz tex/
	tar czf tex_src.tar.gz tex.src/
	mv tex.tar.gz tex_src.tar.gz $(SHARED_FOLDER)

clean:
	rm *.pyc pySkeleton/*.pyc textures/*.pyc batch_processing/*.pyc
	rm roof-error*
	rm roads_*.ac roads_*.eps

