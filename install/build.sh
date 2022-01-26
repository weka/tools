TOOL=wekaconfig
pyinstaller --onefile ${TOOL}.py


TARGET=tarball/$TOOL
mkdir -p $TARGET
cp dist/$TOOL $TARGET
cd tarball
tar cvzf ../${TOOL}.tar $TOOL

