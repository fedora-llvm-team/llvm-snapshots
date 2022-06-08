.PHONY: rpm
rpm:
	rm -rf ~/rpmbuild \
	&& rpmdev-setuptree \
	&& rpmdev-spectool --force -R --get-files --all ./llvm-snapshot-builder.spec \
	&& rpmbuild -ba llvm-snapshot-builder.spec \
	&& tree ~/rpmbuild