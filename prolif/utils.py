import re, textwrap
from math import pi
import numpy as np
from rdkit import Chem
from rdkit import Geometry as rdGeometry


PERIODIC_TABLE = Chem.GetPeriodicTable()
BONDTYPE_TO_RDKIT = {
    "AROMATIC": Chem.BondType.AROMATIC,
    'SINGLE': Chem.BondType.SINGLE,
    'DOUBLE': Chem.BondType.DOUBLE,
    'TRIPLE': Chem.BondType.TRIPLE,
}
BONDORDER_TO_RDKIT = {
    1: Chem.BondType.SINGLE,
    2: Chem.BondType.DOUBLE,
    3: Chem.BondType.TRIPLE,
}

def pdbqt_to_mol2(path):
    from openbabel import pybel
    mols = []
    for m in pybel.readfile("pdbqt", path):
        # necessary to properly add H
        mH = pybel.readstring("pdb", m.write("pdb"))
        mH.addh()
        # need to reassign old charges to mol
        mH.OBMol.SetPartialChargesPerceived(True)
        for i, (atom, old) in enumerate(zip(mH.atoms, m.atoms)):
            if i == len(m.atoms): # stop at new hydrogens
                break
            # assign old charges
            atom.OBAtom.SetPartialCharge(old.partialcharge)
        mols.append(mH)
    return [x.write("mol2") for x in mols]

def update_bonds_and_charges(mol):
    """mdtraj and pytraj don't keep information on bond order, and formal charges.
    Since the given molecule should have all hydrogens added, we can infer
    bond order and charges from the valence."""

    for atom in mol.GetAtoms():
        vtot = atom.GetTotalValence()
        valences = PERIODIC_TABLE.GetValenceList(atom.GetAtomicNum())
        electrons = [ v - vtot for v in valences ]
        # if numbers in the electrons array are >0, the atom is missing bonds or
        # formal charges. If it's <0, it has too many bonds and we must add the
        # corresponding formal charge (we cannot break bonds present in the topology).

        # if the only option is to add a positive charge
        if (len(electrons)==1) and (electrons[0]<0):
            charge = -electrons[0] # positive
            atom.SetFormalCharge(charge)
            mol.UpdatePropertyCache(strict=False)
        else:
            set_electrons = set(electrons)
            neighbors = atom.GetNeighbors()
            # check if neighbor can accept a double / triple bond
            for i,na in enumerate(neighbors, start=1):
                na_vtot = na.GetTotalValence()
                na_valences = PERIODIC_TABLE.GetValenceList(na.GetAtomicNum())
                na_electrons = [ v - na_vtot for v in na_valences ]
                common_electrons = min(set_electrons.intersection(na_electrons), default=np.nan)
                if common_electrons != 0:
                    # if they have no valence need in common but it's the last option
                    if common_electrons is np.nan:
                        if i == len(neighbors): # if it's the last option available
                            charge = -electrons[0] # negative
                            atom.SetFormalCharge(charge)
                            mol.UpdatePropertyCache(strict=False)
                    # if they both need a supplementary bond
                    else:
                        bond = mol.GetBondBetweenAtoms(atom.GetIdx(), na.GetIdx())
                        if common_electrons == 1:
                            bond.SetBondType(Chem.BondType.DOUBLE)
                        elif common_electrons == 2:
                            bond.SetBondType(Chem.BondType.TRIPLE)
                        mol.UpdatePropertyCache(strict=False)
                        break # out of neighbors loop
    Chem.SanitizeMol(mol)

def get_resnumber(resname):
    pattern = re.search(r'(\d+)', resname)
    return int(pattern.group(1))

def get_centroid(coordinates):
    """Centroid for an array of XYZ coordinates"""
    return np.mean(coordinates, axis=0)

def get_ring_normal_vector(centroid, coordinates):
    """Returns a vector that is normal to the ring plane"""
    # A & B are two edges of the ring
    a = rdGeometry.Point3D(*coordinates[0])
    b = rdGeometry.Point3D(*coordinates[1])
    # vectors between centroid and these edges
    ca = centroid.DirectionVector(a)
    cb = centroid.DirectionVector(b)
    # cross product between these two vectors
    normal = ca.CrossProduct(cb)
    # note that cb.CrossProduct(ca) will the normal vector in the opposite direction
    return normal

def angle_between_limits(angle, min_angle, max_angle, ring=False):
    """
    Check if an angle value is between min and max angles in degrees.
    If the angle to check involves a ring, include the angle that would be obtained
    if we had used the other normal vector (same axis but opposite direction).
    """
    if ring and (angle > pi/2):
        mirror_angle = (pi/2) - (angle % (pi/2))
        condition = (min_angle <= angle <= max_angle) or (min_angle <= mirror_angle <= max_angle)
    else:
        condition = (min_angle <= angle <= max_angle)
    return condition
