rm -rf /occt-original || true
mkdir /occt-original
cd /occt-original
tar -xzf /occt/occt.tar.gz --strip-components=1
cp /occt/src/FoundationClasses/TKernel/Standard/Standard_Version.hxx src/FoundationClasses/TKernel/Standard/

diff -ruN /occt-original/ /occt/ > /opencascade.js/src/patches/newPatch.patch
