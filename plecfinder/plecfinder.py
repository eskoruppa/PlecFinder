import os, sys
import numpy as np
from numba import jit
from .PyLk import pylk
from .branching import build_branchtree

from typing import List, Dict, Any, Tuple

# To Do:
# branch writhe is not correctly calculated. Should be dubbled and possibly checked for overlap of upper and lower triangular contributions

########################################################################
########################################################################
########################################################################


def find_plecs(
    conf: np.ndarray,
    min_writhe_density: float,
    plec_min_writhe: float,
    disc_len: float = None,
    no_overlap: bool = True,
    connect_dist: float = 10.0,
    om0: float = 1.76,
    include_wm: bool = False,
    unify_branch_pieces = True
) -> List[Dict[str, Any]]:
    """Calculates the topology of a given configuration.

    Arguments:
    ----------
        conf : np.ndarray
            3D configruation, should be Nx3 numpy array containing the position vectors

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
            - id1 : entrance index
            - id2 : exit index
            - wrdens : writhe density within plectoneme
            - wr : total writhe in plectoneme
            - num_segs : number of contained segments
            - L : length of plectoneme
            - branch_ids : indices of branches and tracers contained in plectoneme

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
            - id : index in tracers list
            - points : list of points tracing the branch, each of which contains an x index and y index for the two pairs consituting the two segments on opposing strands of the superhelix

    """

    # Calculate Writhe Map
    WM = calculate_WM(conf)

    # Consider writhe always to be positive
    pWM = np.sign(np.mean(WM)) * WM

    # Calculate discretization length
    if disc_len is None:
        disc_len = cal_disc_len(conf)

    ###################
    # Trace Plectonemes

    # detect traces and assign them to branches
    branches, tracers = _find_branches(
        pWM, min_writhe_density, disc_len, connect_dist=connect_dist, om0=om0
    )
    
    #######################################
    #######################################
    
    if len(branches) > 0:
        if no_overlap:
            branches = _remove_branch_overlap(pWM, branches)
            branches, tracers = _remove_flagged_branches(branches, tracers)
        ##################
        # resolve branch conflicts
        branches = _resolve_inconsistent_branches(pWM, branches)
        branches, tracers = _remove_flagged_branches(branches, tracers)

        ##################
        # collect branches into plectonemes
        combbranches, contained_branch_ids = _combine_branches(
            pWM, branches, min_writhe_density, disc_len, om0
        )
        
        plecs = _define_plecs(
            pWM, combbranches, min_writhe_density, plec_min_writhe, disc_len, om0
        )
        plec_branch_ids = [contained_branch_ids[int(plec[6])] for plec in plecs]

        branches = [branches[item] for sublist in plec_branch_ids for item in sublist]
        tracers = [tracers[item] for sublist in plec_branch_ids for item in sublist]
    else:
        # if there are no branches found empty lists are initialized
        plecs = list()
        plec_branch_ids = list()

    ##################
    # unify branches
    if unify_branch_pieces:
        treebranches = unify_branches(branches)
        branches, tracers = _remove_flagged_branches(branches, tracers)
    ############################
    # assign topology dictionary

    plecdicts = list()
    for i, plec in enumerate(plecs):
        plecdict = dict()
        plecdict["id1"] = int(plec[0])
        plecdict["id2"] = int(plec[1])
        plecdict["wrdens"] = plec[2]
        plecdict["wr"] = plec[3]
        plecdict["num_segs"] = int(plec[4])
        plecdict["L"] = int(plec[4]) * disc_len
        plecdict["branch_ids"] = plec_branch_ids[i]
        plecdicts.append(plecdict)

    branchdicts = list()
    tracerdicts = list()
    for i, branch in enumerate(branches):
        branchdict = dict()
        tracerdict = dict()

        if branch[1] > branch[3]:
            print(
                f"Warning: branch terminates in lower triangle: ({branch[1]}, {branch[3]})"
            )
            # raise ValueError(f'branch terminates in lower triangle')

        branch_wr = 2 * _cal_branch_writhe(WM, *branch)
        downstream_wr = _cal_branch_writhe(
            WM, branch[0], branch[3], branch[0], branch[3]
        )

        branchdict["id"] = i
        branchdict["x1"] = int(branch[0])
        branchdict["x2"] = int(branch[1])
        branchdict["y1"] = int(branch[2])
        branchdict["y2"] = int(branch[3])
        branchdict["wr"] = branch_wr
        branchdict["wr_down"] = downstream_wr

        tracerdict["id"] = i
        tracerdict["points"] = [[pt[0], pt[1]] for pt in tracers[i]]

        branchdicts.append(branchdict)
        tracerdicts.append(tracerdict)

    topol = dict()
    topol["N"] = len(WM)
    topol["L"] = len(WM) * disc_len
    topol["disc_len"] = disc_len
    topol["plecs"] = plecdicts
    topol["branches"] = branchdicts
    topol["tracers"] = tracerdicts
    topol["wr"] = np.sum(WM)
    topol["num_plecs"] = len(plecdicts)
    topol["num_branches"] = len(branchdicts)
    topol["num_tracers"] = len(tracerdicts)
    topol["no_overlap"] = no_overlap

    if include_wm:
        topol["wm"] = WM
        # ~ topol['pwm'] = pWM

    return topol


########################################################################
########################################################################
########################################################################


########################################################################
# Calculate the writhe map
def calculate_WM(conf):
    WM = pylk.writhemap(conf)
    WM[:, 0] = 0
    WM[:, -1] = 0
    WM[0, :] = 0
    WM[-1, :] = 0
    return WM


########################################################################
# remove tracers for removed branches

# @jit(nopython=True, cache=True)
def _remove_flagged_branches(branches, tracers):
    """
    renmove branches and tracers for which the branch is tagged with x1 = -1
    """
    nbranches = list()
    ntracers = list()
    for i in range(len(branches)):
        if branches[i][0] != -1:
            nbranches.append(branches[i])
            ntracers.append(tracers[i])
    return nbranches, ntracers

########################################################################
# unify branches

def unify_branches(branches):
    treeroots, treebranches = build_branchtree(branches)
    for treebranch in treebranches:
        if treebranch['root'][0] == -1:
            continue
        if len(treebranch["branches"]) == 1:
            subbr = treebranch["branches"][0]
            treebranch["root"][1] = subbr['root'][1]
            treebranch["root"][2] = subbr['root'][2]
            treebranch['branches'] = subbr['branches']
            
            # flag subbranch for deletition
            subbr['root'][0] = -1
    return treebranches


########################################################################
# find branches


# @jit(nopython=True, cache=True)
def _find_branches(
    WM: np.ndarray,
    min_writhe_density: float,
    disc_len: float,
    connect_dist=10.0,
    om0=1.76,
):
    """
    Assigns branch tracers and branches
    """
    connect_segs = int(np.ceil(connect_dist / disc_len))
    wr2dens_conv_fac = 2 * np.pi / om0
    minwrdens_convfac = min_writhe_density / wr2dens_conv_fac
    minwr_per_seg = disc_len * minwrdens_convfac

    pairs = _find_pairs(WM, minwr_per_seg)

    ####################################################################
    ####################################################################
    # combine pairs into tracers

    tracers = list()
    tracer_xlims = list()
    tracer_ylims = list()
    for pair in pairs:
        largest_match_id = -1
        largest_match_len = 0
        for i, tracer in enumerate(tracers):
            txlim = tracer_xlims[i]
            tylim = tracer_ylims[i]
            xdisp = pair[0] - txlim[1]
            if xdisp > connect_segs:
                continue
            if not (
                np.abs(tylim[0] - pair[1]) <= connect_segs
                or np.abs(pair[1] - tylim[1]) <= connect_segs
                or tylim[0] <= pair[1] <= tylim[1]
            ):
                continue
            if len(tracer) > largest_match_len:
                largest_match_id = i
                largest_match_len = len(tracer[0])

        if largest_match_len == 0:
            xlim = np.array([pair[0], pair[0]])
            ylim = np.array([pair[1], pair[1]])
            tracer = [pair]
            tracers.append(tracer)
            tracer_xlims.append(xlim)
            tracer_ylims.append(ylim)
        else:
            tracer_xlims[largest_match_id][1] = pair[0]
            if pair[1] > tracer_ylims[largest_match_id][1]:
                tracer_ylims[largest_match_id][1] = pair[1]
            if pair[1] < tracer_ylims[largest_match_id][0]:
                tracer_ylims[largest_match_id][0] = pair[1]
            tracers[largest_match_id].append(pair)

    ####################################################################
    ####################################################################
    # Assign branches to tracers. Only tracers satisfying the writhe density condition are promoted
    # to branches

    branches = list()
    branchtracers = list()
    for i, tracer in enumerate(tracers):
        ################################################################
        # asign branch
        xlim = tracer_xlims[i]
        ylim = tracer_ylims[i]
        wr = (
            np.sum(WM[int(xlim[0]) : int(xlim[1]) + 1, int(ylim[0]) : int(ylim[1]) + 1])
            * 2
        )
        l_plec = _maxint(xlim[1] - xlim[0] + 1, ylim[1] - ylim[0] + 1) * disc_len
        wrdens = wr2dens_conv_fac * wr / l_plec
        if wrdens < min_writhe_density:
            continue
        # ~ branch = np.array([xlim[0],xlim[1],ylim[0],ylim[1],wr,wrdens])
        branch = np.array([xlim[0], xlim[1], ylim[0], ylim[1]])
        branches.append(branch)

        ################################################################
        # calculate tracer band
        tracerband = np.zeros((int(xlim[1] + 1 - xlim[0]), 2))
        tracerband[:, 0] = np.arange(int(xlim[0]), int(xlim[1]) + 1)

        # this is somewhat awkward..  was a quick fix
        tcrmat = np.zeros((len(tracer), 5))
        for j in range(len(tracer)):
            tcrmat[j] = tracer[j]

        Nelem = int(xlim[1] - xlim[0])
        for j in range(Nelem + 1):
            jelems = tcrmat[tcrmat[:, 0] == j + xlim[0]]
            if len(jelems) == 0:
                if j == 0:
                    tracerband[0, 1] = ylim[1]
                elif j == Nelem:
                    tracerband[Nelem, 1] = ylim[0]
                else:
                    tracerband[j, 1] = -1
            else:
                tracerband[j, 1] = jelems[np.argmax(jelems[:, 3]), 1]

        # interpolate -1 values
        setvals = tracerband[tracerband[:, 1] != -1, 0] - tracerband[0, 0]
        setvals = setvals.astype("int32")
        for k in range(len(setvals) - 1):
            if setvals[k + 1] > setvals[k] + 1:
                num = setvals[k + 1] - setvals[k]
                v1 = tracerband[setvals[k], 1]
                v2 = tracerband[setvals[k + 1], 1]
                dv = (v2 - v1) / num
                for ip in range(1, num):
                    tracerband[setvals[k] + ip, 1] = v1 + ip * dv

        branchtracers.append(tracerband)
        ################################################################
    return branches, branchtracers


# @jit(nopython=True, cache=True)
def _find_pairs(WM: np.ndarray, minwr_per_seg: float):
    """
    find pairs based on minimum writhe density
    mirrors segments in bottom half to top and
    sorts them
    """
    nbp = len(WM)
    # define pairs
    pairs = np.zeros((nbp, 5))
    for i in range(nbp):
        pairs[i, 0] = i
        summed = np.sum(WM[i, :])
        j = np.argmax(WM[i, :])
        pairs[i, :4] = [i, j, summed, WM[i, j] * 2]
        if summed > minwr_per_seg:
            pairs[i, 4] = 1

    mmpairs = list()
    # filter and mirror
    for pair in pairs:
        if pair[4] == 0:
            continue
        mpair = np.copy(pair)
        if mpair[1] < mpair[0]:
            mpair[0] = pair[1]
            mpair[1] = pair[0]
        mmpairs.append(mpair)

    # sort pairs
    mpairs = np.zeros((len(mmpairs), 5))
    for i in range(len(mmpairs)):
        mpairs[i] = mmpairs[i]
    mpairs = [mpairs[i] for i in np.argsort(mpairs[:, 0])]
    return mpairs


########################################################################
# remove branch overlap


# @jit(nopython=True, cache=True)
def _remove_branch_overlap(WM: np.ndarray, branches):
    """
    removes only overlap in y direction as
    overlap in the x direction is not possible.
    """
    X1 = 0
    X2 = 1
    Y1 = 2
    Y2 = 3

    for i in range(len(branches) - 1):
        if branches[i][Y2] < branches[i][Y1]:
            continue
        for j in range(i + 1, len(branches)):
            if branches[j][Y2] < branches[j][Y1]:
                continue

            xlim1 = branches[i][0:2]
            ylim1 = branches[i][2:4]
            xlim2 = branches[j][0:2]
            ylim2 = branches[j][2:4]
            ylim1, ylim2 = _remove_branchpair_overlap(WM, xlim1, xlim2, ylim1, ylim2)
            xlim1, ylim2 = _remove_branchpair_overlap(WM, ylim1, xlim2, xlim1, ylim2)
            ylim1, xlim2 = _remove_branchpair_overlap(WM, xlim1, ylim2, ylim1, xlim2)
            xlim1, xlim2 = _remove_branchpair_overlap(WM, ylim1, ylim2, xlim1, xlim2)

            branches[i][0:2] = xlim1
            branches[i][2:4] = ylim1
            branches[j][0:2] = xlim2
            branches[j][2:4] = ylim2

    # for i,branch in enumerate(branches[:-1]):
    for i, branch in enumerate(branches):
        if branch[Y1] > branch[Y2] or branch[X1] > branch[X2]:
            branches[i][0] = -1
    # ~ branches = [branch for branch in branches if branch[Y1] <= branch[Y2]]
    return branches


# @jit(nopython=True, cache=True)
def _remove_branchpair_overlap(WM, xlim1, xlim2, ylim1, ylim2):
    lim1 = ylim1
    lim2 = ylim2
    if lim1[1] < lim2[0] or lim2[1] < lim1[0]:
        # no overlap
        return ylim1, ylim2

    scenario = 0
    rev = 0
    # case 1
    if lim1[0] <= lim2[1] <= lim1[1] and lim2[0] <= lim1[0]:
        xlima = xlim1
        ylima = ylim1

        xlimb = xlim2
        ylimb = ylim2
        scenario = 1

    # case 2
    if lim2[0] <= lim1[1] <= lim2[1] and lim1[0] <= lim2[0]:
        xlima = xlim2
        ylima = ylim2

        xlimb = xlim1
        ylimb = ylim1
        rev = 1
        scenario = 1

    # case 3
    if lim2[1] < lim1[1] and lim2[0] > lim1[0]:
        xlima = xlim1
        ylima = ylim1

        xlimb = xlim2
        ylimb = ylim2
        scenario = 2

    # case 4
    if lim1[1] < lim2[1] and lim1[0] > lim2[0]:
        xlima = xlim2
        ylima = ylim2

        xlimb = xlim1
        ylimb = ylim1
        rev = 1
        scenario = 2

    if scenario == 1:
        a = int(ylima[0])
        b = int(ylimb[1])
        wra = np.sum(WM[int(xlima[0]) : int(xlima[1]) + 1, a : b + 1])
        wrb = np.sum(WM[int(xlimb[0]) : int(xlimb[1]) + 1, a : b + 1])

        if wra >= wrb:
            ylimb[1] = a - 1
        else:
            ylima[0] = b + 1

    else:
        wra = np.sum(
            WM[int(xlima[0]) : int(xlima[1]) + 1, int(ylima[0]) : int(ylima[1]) + 1]
        )
        wrb = np.sum(
            WM[int(xlimb[0]) : int(xlimb[1]) + 1, int(ylimb[0]) : int(ylimb[1]) + 1]
        )
        if wra >= wrb:
            ylimb[1] = ylimb[0] - 1
        else:
            ylima[1] = ylima[0] - 1

    if rev:
        return ylimb, ylima
    else:
        return ylima, ylimb


########################################################################
########################################################################

def _resolve_inconsistent_branches(WM: np.ndarray, branches):
    # we assume that overlap was already removed 
    n = len(branches)
    
    # count number of downsteam branches
    downstream_counts = list()
    for i in range(n):
        count = 0
        for j in range(i+1):
            if _is_downstream(branches[i][0],branches[i][3],branches[j][0],branches[j][3]):
                count += 1
        downstream_counts.append(count)
    
    # Check backward conflicts
    for i in range(1,n):
        a1 = int(branches[i][0])
        a2 = int(branches[i][3])
        conflict_wr = 0
        conflict_ids = []
        for j in range(0,i):
            if branches[j][0] == -1:
                continue
            
            b1 = branches[j][0]
            b2 = branches[j][3]
            # if i is inside rang of j but not downstream
            if b1 < a1 < b2 and not _is_downstream(b1,b2,a1,a2):
                wr = _cal_branch_writhe(WM,*branches[j])
                conflict_ids.append(j)
                conflict_wr += wr
        
        if conflict_wr > 0:
            ref_wr = _cal_branch_writhe(WM,*branches[i])
            if ref_wr > conflict_wr:
                for cid in conflict_ids:
                    branches[cid][0] = -1
            else:
                # check forward conflicts
                #
                #
                #
                #
                #
                branches[i][0] = -1
        
    return branches


########################################################################
########################################################################



# @jit(nopython=True, cache=True)
def _minint(a: int, b: int) -> int:
    """
    return minimum of two args
    """
    if a < b:
        return a
    return b


# @jit(nopython=True, cache=True)
def _maxint(a: int, b: int) -> int:
    """
    return maximum of two args
    """
    if a > b:
        return a
    return b


# @jit(nopython=True, cache=True)
def _is_downstream(a1, a2, b1, b2):
    if (a1 <= b1 <= a2) and (a1 <= b2 <= a2):
        return True
    return False


# @jit(nopython=True, cache=True)
def _cal_branch_writhe(WM, X1, X2, Y1, Y2):
    return np.sum(WM[int(X1) : int(X2) + 1, int(Y1) : int(Y2) + 1])


# def _cal_branch_writhe(WM, branch):
#     X1 = 0
#     X2 = 1
#     Y1 = 2
#     Y2 = 3
#     return np.sum(
#         WM[int(branch[X1]) : int(branch[X2]) + 1, int(branch[Y1]) : int(branch[Y2]) + 1]
#     )


# @jit(nopython=True, cache=True)
def _can_connect_downstream_branches(a1, a2, b1, b2, WM, minwr_per_seg):
    a1 = int(a1)
    a2 = int(a2)
    b1 = int(b1)
    b2 = int(b2)

    if not _is_downstream(a1, a2, b1, b2):
        return False

    wr = 0
    wr += np.sum(WM[a1:b1, b2 + 1 : a2 + 1])
    wr += np.sum(WM[a1:b1, 0 : b2 + 1])
    wr += np.sum(WM[b1:, b2 + 1 : a2 + 1])

    num_segs = _maxint(b1 - a1, a2 - b2)
    wr_per_seg = wr / num_segs

    if wr_per_seg > minwr_per_seg:
        return True
    return False


# @jit(nopython=True, cache=True)
def _combine_branches(WM, branches, min_writhe_density, disc_len, om0):
    """
    combine downstream branches
    """
    X1 = 0
    X2 = 1
    Y1 = 2
    Y2 = 3

    wr2dens_conv_fac = 2 * np.pi / om0
    minwrdens_convfac = min_writhe_density / wr2dens_conv_fac
    minwr_per_seg = disc_len * minwrdens_convfac

    combbranch = list()
    contained_branch_ids = list()

    for i in range(len(branches)):
        p1 = branches[i][X1]
        p2 = branches[i][Y2]

        new_plec = True
        for j, plec in enumerate(combbranch):
            a1 = plec[X1]
            a2 = plec[Y2]
            b1 = plec[X2]
            b2 = plec[Y1]

            if _is_downstream(a1, a2, p1, p2):
                new_plec = False
                contained_branch_ids[j].append(i)

                if _is_downstream(b1, b2, p1, p2):
                    if _can_connect_downstream_branches(
                        a1, a2, p1, p2, WM, minwr_per_seg
                    ):
                        plec[X2] = _maxint(plec[X2], branches[i][X2])
                        plec[Y1] = _minint(plec[Y1], branches[i][Y1])
                    else:
                        if _cal_branch_writhe(WM, *branches[i]) > _cal_branch_writhe(
                            WM, *plec
                        ):
                            plec = branches[i]
                else:
                    plec[X2] = _maxint(plec[X2], branches[i][X2])
                    plec[Y1] = _minint(plec[Y1], branches[i][Y1])
                break

        if new_plec:
            combbranch.append(np.copy(branches[i]))
            contained_branch_ids.append([i])
    return combbranch, contained_branch_ids


########################################################################
########################################################################


# @jit(nopython=True, cache=True)
def _define_plecs(WM, combbranches, min_writhe_density, min_writhe, disc_len, om0):
    wr_tot = np.sum(WM)

    wr2dens_conv_fac = 2 * np.pi / om0
    # minwrdens_convfac = min_writhe_density / wr2dens_conv_fac
    # minwr_per_seg = disc_len * minwrdens_convfac

    candidate_plecs = list()
    for combbranch in combbranches:
        candidate_plec = np.array(
            [combbranch[0], combbranch[3], combbranch[0], combbranch[3]]
        )
        candidate_plecs.append(candidate_plec)

    candidate_plecs = _remove_branch_overlap(WM, candidate_plecs)

    plecs = list()
    for i, candidate_plec in enumerate(candidate_plecs):
        wr = _cal_branch_writhe(WM, *candidate_plec)
        num_segs = candidate_plec[1] - candidate_plec[0] + 1
        l_plec = num_segs * disc_len
        if l_plec <= 0:
            continue
        wrdens = wr2dens_conv_fac * wr / l_plec

        if wrdens >= min_writhe_density and wr >= min_writhe:
            plec = np.array(
                [candidate_plec[0], candidate_plec[1], wrdens, wr, num_segs, wr_tot, i]
            )
            plecs.append(plec)
    return plecs


########################################################################
########################################################################
########################################################################
########################################################################
########################################################################
########################################################################


# @jit(nopython=True, cache=True)
def _find_overlap(plecs):
    for i in range(1, len(plecs)):
        for j in range(i):
            if (
                plecs[j][0] <= plecs[i][0] <= plecs[j][1]
                or plecs[j][0] <= plecs[i][1] <= plecs[j][1]
                or plecs[i][0] <= plecs[j][0] <= plecs[i][1]
                or plecs[i][0] <= plecs[j][1] <= plecs[i][1]
            ):
                return True
    return False


########################################################################


# @jit(nopython=True, cache=True)
def _tracer_inside_plec(tracer, plec_entry, plec_last, combine_segdist):
    if (
        tracer[0] < plec_entry[0]
        or tracer[0] > plec_entry[1]
        or tracer[1] < plec_entry[0]
        or tracer[1] > plec_entry[1]
    ):
        if (
            np.abs(plec_last[0] - tracer[0]) <= combine_segdist
            and np.abs(plec_last[1] - tracer[1]) <= combine_segdist
        ):
            return True
        return False
    else:
        return True


########################################################################
########################################################################
########################################################################


def cal_disc_len(conf):
    """returns the mean discretization lenght."""
    if len(np.shape(conf)) == 2:
        conf = np.array([conf])
    return np.round(__cal_disc_len(conf), decimals=8)


# @jit(nopython=True)
def __cal_disc_len(conf):
    dlen = 0.0
    for s in range(len(conf)):
        for i in range(len(conf[0]) - 1):
            dlen += np.linalg.norm(conf[s, i + 1] - conf[s, i])
    return dlen / (len(conf) * (len(conf[0]) - 1))


########################################################################
########################################################################
########################################################################

if __name__ == "__main__":
    from .IOPolyMC.iopolymc import read_state, load_xyz
    from .branching import build_branchtree

    
    xyzfn = '/home/pol_schiessel/ensk996e/Projects/MultiPlec/Paper/sims/dump/f0p4_r3.xyz'
    xyz = load_xyz(xyzfn)
    
    configs = xyz["pos"]

    min_writhe_density = 0.01
    plec_min_writhe = 0.5
    connect_dist = 10.0

    for i, config in enumerate(configs):
        
        if i < 13 and i not in [0,12]:
            continue
        
        topol = find_plecs(
            config,
            min_writhe_density,
            plec_min_writhe,
            disc_len=None,
            no_overlap=True,
            connect_dist=connect_dist,
        )
        # sys.exit()
        from .plottopol import plot_topol
        
        plot_topol(topol)

        # treeroots, treebranches = build_branchtree(topol)
        # plot_branchtree(treebranches,topol)


