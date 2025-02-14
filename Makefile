

SOURCE=SOURCES/weka-tools.tgz
SPECS=$(wildcard SPECS/*)

TARG=RPMS/noarch/weka-tools-8.10-1.el8.x86_64.rpm
.PHONY: all clean Makefile

all: ${SOURCE} ${TARG}
	echo Done

${TARG}: ${SOURCE} ${SPECS} 
	rpmbuild --define "_topdir ${CURDIR}" -ba ${SPECS}

${SOURCE}:
	mkdir -p SOURCES
	tar -czvf ${SOURCE} --exclude-from=tar_excludes.txt *

clean:
	rm -rf ${TARG} BUILD BUILDROOT RPMS SRPMS ${SOURCE}/*
