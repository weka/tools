

SOURCE=SOURCES/weka-tools.tgz
SPECS=$(wildcard SPECS/*.spec)

TARG=RPMS/noarch/weka-tools-8.10-1.el8.x86_64.rpm
.PHONY: all clean Makefile

all: ${SOURCE} ${TARG}
	echo Done

${TARG}: ${SOURCE} ${SPECS} 
	rpmbuild --define "_topdir ${CURDIR}" -ba ${SPECS}

${SOURCE}:
	mkdir -p SOURCES
	$(eval VERS := $(shell date +%C%y.%m.%d))
	echo "%define _tools_version ${VERS}" > SPECS/version.inc
	tar -czvf ${SOURCE} --exclude-from=tar_excludes.txt *

clean:
	rm -rf ${TARG} BUILD BUILDROOT RPMS SRPMS ${SOURCE}/*
