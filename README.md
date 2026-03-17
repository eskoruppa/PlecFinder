# PlecFinder
Python package for analyzing the topology of polymer configurations

## Install

### Required packages:
- numpy
- scipy
- numba
- cython
- matplolib

##### Package installation
```
git clone --recurse-submodules -j8 https://github.com/eskoruppa/PlecFinder.git
pip install PlecFinder/.
```

### Example
```
python
import plecfinder as pf
pf.testrun()
```

### How to use:

The core functionality is contained in the find_plectonemes function:

```
topol = pf.find_plecs((conf,min_writhe_density,plec_min_writhe ,disc_len=None, no_branch_overlap=True ,connect_dist=10.0, om0=1.76,include_wm=False))
```

Arguments:
----------
    conf : np.ndarray
        3D configruation, should be Nx3 numpy array containing the position vectors (dimension Nx3)
    
    min_writhe_dens : float   
        minimum writhe density for a region to be detected as as plectonemic coil
    
    plec_min_writhe : float
        minimum writhe for a coil to be identified as a plectoneme
    
    disc_len :  float, optional       
        discretization length, if None discretization length will be calculated based on 
        provided configuration (default: None)
    
    no_overlap: bool, optional
        remove overlap of neighboring branches (default: True)
        Note that no_overlap=True is required for building plectoneme structure
    
    connect_dist: float, optional
        distance in nm for which neighboring points of sufficient writhedensity points are connected to form a branch (default: 10nm)
    
    om0: float, optional
        intrinsic twist (default: 1.76 rad/nm)
    
    include_wm: bool, optional
        include writhemap in return dictionary. This may lead to large memory consumption. (default: False)

Returns:
----------
    topology dictionary:
    
        ### Keys:
        - N :               int - number of chain segments
        - L :               float - Length of chain
        - disc_len :        float - discretization length (segment size)
        - wr :              float - total writhe in configuration
        - num_plecs :       int - number of plectonemes
        - num_branches :    list of branches
        - num_tracers :     list of tracers
        - plecs :           list of plectonemes
        - branches :        list of branches
        - tracers :         list of tracers
        - wm :              NxN ndarray - writhe map (this key is optional)
        - no_overlap :      bool - branch overlap removed
    
        Elements of the plectoneme list are dictionaries themselves. 
        ### Plectoneme Keys:
        - id1 :         entrance index
        - id2 :         exit index
        - wrdens :      writhe density within plectoneme
        - wr :          total writhe in plectoneme
        - num_segs :    number of contained segments
        - L :           length of plectoneme
        - branch_ids :  indices of branches and tracers contained in plectoneme
    
        Banches and Tracers are likewise dictionaries. 
        ### Branch keys:
        - id : index in branches list
        - x1 : entrance x id
        - x2 : exit x id
        - y1 : entrance y id
        - y2 : exit y id
        - wr : writhe within branch
        - wr_down : total writhe downstream relative to the given branch 
    
        ### Tracer keys:
        - id :      index in tracers list
        - points :  list of points tracing the branch, each of which contains an x index and y index for the two pairs consituting the two segments on opposing strands of the superhelix 


​        
## Writhe Map
Methods to calculate the writhe map are contained in the directory CalWM/. The is a cython, a numba and a bare python implementation of method 1 from Klenin et al (Ref. [1]). Cython is recommended as it is several times faster than the numba implementation but it requires compilation. To compile execute the bash script: ./compile.sh


1. Klenin, K., & Langowski, J. (2000). Computation of writhe in modeling of supercoiled DNA. Biopolymers, 54(5), 307–317. [https://doi.org/10.1002/1097-0282(20001015)54:5<307::AID-BIP20>3.0.CO;2-Y](https://doi.org/10.1002/1097-0282(20001015)54:5<307::AID-BIP20>3.0.CO;2-Y)
