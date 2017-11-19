import sys
import os
sys.path.insert(0, os.getcwd() + "/pysrc/cellh5/")
from cellh5 import cellh5,cellh5write
import pytest

ch5name = "test.ch5"
defbase = "/definition/"
samplebase = "/sample/0/"
@pytest.mark.parametrize("ch5name", [(ch5name)])
def test_empty_ch5(ch5name):
    cfw = cellh5write.CH5FileWriter(ch5name)
    cfw.close()
    assert os.path.exists(ch5name)
    with cellh5.ch5open(ch5name) as fh:
        assert fh.get_file_handle()[samplebase]
        assert fh.get_file_handle()[defbase+"feature"]
        assert fh.get_file_handle()[defbase+"image"]
        assert fh.get_file_handle()[defbase+"object"]
@memoize
def add(x,y):
    return x+y
add(3,4)
add
def test_tear_down():
    os.remove(ch5name)
    
