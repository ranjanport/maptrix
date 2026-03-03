#!/bin/bash
set -e

cd assets/docs/
make clean
sphinx-apidoc -o source ../../src/maptrix -f  -M
make html

cd ../../

echo "Docs available at assets/docs/build/html/index.html"