################################################################################
#
# Copyright (C) 2022-2023 Advanced Micro Devices, Inc. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
################################################################################

from .Activation import ActivationType
from .Common import printExit
from .TensileInstructions import DataType
from . import Hardware
from . import Properties
from .SolutionStructs import getBiasDataTypeListDefault
from .SolutionStructs import Solution as OriginalSolution
from .Utils import state, state_key_ordering

from . import Common
from . Common import globalParameters

@state_key_ordering
class FreeIndex:
    StateKeys = ['isA', 'i', 'c', 'd']

    def __init__(self, isA, i=None, c=None, d=None):
        self.isA = isA
        self.i = i # index into A or B (depending on isA)
        self.c = c
        self.d = d

@state_key_ordering
class BatchIndex:
    StateKeys = ['a', 'b', 'c', 'd']
    def __init__(self, a=None, b=None, c=None, d=None):
        self.a = a
        self.b = b
        self.c = c
        self.d = d

@state_key_ordering
class BoundIndex:
    StateKeys = ['a', 'b', 'aMirror', 'bMirror']
    def __init__(self, a=None, b=None, aMirror=False, bMirror=False):
        self.a = a
        self.b = b
        self.aMirror = aMirror
        self.bMirror = bMirror


class ProblemType:
    StateKeys = ['operationIdentifier', 'transA', 'transB', 'aType', 'bType', 'cType', 'dType', 'eType', 'computeType',
                 'useBeta', 'useBias', 'biasSrcWhiteList', 'useE', 'useScaleDVec', 'biasDataTypeWhiteList', 'highPrecisionAccumulate',
                 'useInitialStridesAB', 'useInitialStridesCD', 'stridedBatched', 'groupedGemm',
                 'useGradient', 'activationType', 'activationArgLength', 'activationComputeDataType', 'activationNoGuard',
                 'sparseA', 'f32XdlMathOp', 'supportDeviceUserArguments']
    @classmethod
    def FromOriginalState(cls, d):
        indices = [None]*d['TotalIndices']
        freeIndices  = []
        batchIndices = []
        boundIndices = []

        for i in d['IndicesSummation']:
            bi = BoundIndex(aMirror=('MirrorDimsA' in d and i in d['MirrorDimsA']),
                            bMirror=('MirrorDimsB' in d and i in d['MirrorDimsB']))
            indices[i] = bi
            boundIndices.append(bi)

        for i in range(0,d["NumIndicesC"]):
            if i in d['IndicesBatch']:
                bi = BatchIndex(c=i, d=i)
                indices[i] = bi
                batchIndices.append(bi)
            else:
                assert i in d['IndicesFree']
                if i in d['IndexAssignmentsA']:
                    fi = FreeIndex(isA=True, i=d["IndexAssignmentsA"].index(i), c=i, d=i)
                elif i in d['IndexAssignmentsB']:
                    fi = FreeIndex(isA=False, i=d["IndexAssignmentsB"].index(i), c=i, d=i)
                else:
                    raise RuntimeError("free index %u not in ia or ib"%i)
                indices[i] = fi
                freeIndices.append(fi)

        for ia, ic in enumerate(d['IndexAssignmentsA']):
            indices[ic].a = ia

        for ib, ic in enumerate(d['IndexAssignmentsB']):
            indices[ic].b = ib

        for idx in indices:
            assert idx is not None
            idxState = state(idx)
            for (key, value) in list(idxState.items()):
                assert value is not None

        rv = cls()
        rv.indices = indices
        rv.freeIndices = freeIndices
        rv.batchIndices = batchIndices
        rv.boundIndices = boundIndices
        rv.aDims = len(d['IndexAssignmentsA'])
        rv.bDims = len(d['IndexAssignmentsB'])
        rv.cDims = d['NumIndicesC']
        rv.dDims = rv.cDims

        rv.aConjugate = d['ComplexConjugateA']
        rv.bConjugate = d['ComplexConjugateB']

        srcType = DataType(d['DataType'])
        dstType = DataType(d['DestDataType']) if 'DestDataType' in d else srcType
        computeType = DataType(d['ComputeDataType']) if 'ComputeDataType' in d else dstType

        rv.transA = bool(d['TransposeA'])
        rv.transB = bool(d['TransposeB'])
        rv.aType = srcType
        rv.bType = srcType
        rv.cType = dstType
        rv.dType = dstType
        rv.eType = computeType
        # we already checked the src/dst/compute types are supported and well-assigned in SolutionStruct
        rv.alphaType = computeType
        rv.betaType  = computeType
        rv.computeType = computeType

        rv.highPrecisionAccumulate = False
        if 'HighPrecisionAccumulate' in d:
            rv.highPrecisionAccumulate = d['HighPrecisionAccumulate']

        rv.useInitialStridesAB = False
        if 'UseInitialStridesAB' in d:
            rv.useInitialStridesAB = d['UseInitialStridesAB']
        rv.useInitialStridesCD = False
        if 'UseInitialStridesCD' in d:
            rv.useInitialStridesCD = d['UseInitialStridesCD']

        rv.stridedBatched = True
        if 'StridedBatched' in d:
          rv.stridedBatched = d['StridedBatched']

        rv.groupedGemm = False
        if 'GroupedGemm' in d:
          rv.groupedGemm = d['GroupedGemm']

        rv.setConstStrideA = []
        if 'SetConstStrideA' in d:
            rv.setConstStrideA = d['SetConstStrideA']
        rv.setConstStrideB = []
        if 'SetConstStrideB' in d:
            rv.setConstStrideB = d['SetConstStrideB']

        rv.mirrorDimsA = d['MirrorDimsA'] if 'MirrorDimsA' in d else []
        rv.mirrorDimsB = d['MirrorDimsB'] if 'MirrorDimsB' in d else []

        rv.useBeta = True
        if 'UseBeta' in d:
            rv.useBeta = d['UseBeta']

        rv.useBias               = False
        rv.biasDataTypeWhiteList = []
        rv.biasSrcWhiteList = []
        rv.setConstStrideBias = []
        if 'UseBias' in d:
            rv.useBias = d['UseBias']
            if 'BiasDataTypeList' in d:
                d["BiasDataTypeList"].sort()  # Sort to make sure names are unique
                rv.biasDataTypeWhiteList = d['BiasDataTypeList']
            else:
                rv.biasDataTypeWhiteList = getBiasDataTypeListDefault(d)
            if 'BiasSrc' in d:
                m = ["A", "B", "C", "D"]
                rv.biasSrcWhiteList = [m.index(d['BiasSrc'])]
            if 'SetConstStrideBias' in d:
                rv.setConstStrideBias = d['SetConstStrideBias']

        rv.useE = False
        if 'UseE' in d:
            rv.useE = d['UseE']

        rv.useGradient = False
        if 'Gradient' in d:
            rv.useGradient = d["Gradient"]

        rv.useScaleDVec = False
        if 'UseScaleDVec' in d:
            rv.useScaleDVec = d['UseScaleDVec']

        rv.batched = d['Batched']

        rv.activationType      = ActivationType('none')
        rv.activationArgLength = 0
        if 'ActivationType' in d:
            rv.activationType = ActivationType(d['ActivationType'])
            rv.activationArgLength = len(rv.activationType.getAdditionalArgStringList())
        rv.activationComputeDataType = DataType(d['ActivationComputeDataType'])
        rv.activationNoGuard = False
        if 'ActivationNoGuard' in d:
            rv.activationNoGuard = d["ActivationNoGuard"]
        if 'ActivationComputeDataType' in d:
            rv.activationComputeDataType = DataType(d['ActivationComputeDataType'])
        else:
            rv.activationComputeDataType = DataType(d['ComputeDataType'] if rv.activationHPA else \
                                                    d['DestDataType'])
        rv.sparseA = False
        if 'SparseA' in d:
            rv.sparseA = d['SparseA']

        rv.f32XdlMathOp = DataType(d['F32XdlMathOp']) if 'F32XdlMathOp' in d else DataType(0)

        rv.supportDeviceUserArguments = False
        if 'SupportUserArgs' in d:
            rv.supportDeviceUserArguments = d['SupportUserArgs']
        return rv

    def __init__(self, freeIndices=None, batchIndices=None, boundIndices=None, aDims=None, bDims=None, cDims=None, dDims=None):
        self.freeIndices  = freeIndices
        self.batchIndices = batchIndices
        self.boundIndices = boundIndices
        self.aDims = aDims
        self.bDims = bDims
        self.cDims = cDims
        self.dDims = dDims

    @property
    def indexNames(self):
        aNames = ['_'] * self.aDims
        bNames = ['_'] * self.bDims
        cNames = ['_'] * self.cDims

        allIndexNames = 'ijklmnopqrstuvwxyz'
        index = 0

        dNames = list([allIndexNames[index+i] for i in range(self.cDims)])
        index += len(dNames)

        sumNames = list([allIndexNames[index+i] for i in range(len(self.boundIndices))])
        index += len(sumNames)

        for free in self.freeIndices:
            if free.isA:
                aNames[free.i ] = dNames[free.d]
            else:
                bNames[free.i ] = dNames[free.d]
            cNames[free.c] = dNames[free.d]

        for batch in self.batchIndices:
            name = dNames[batch.d]
            aNames[batch.a] = name
            bNames[batch.b] = name
            cNames[batch.c] = name

        for i, bound in enumerate(self.boundIndices):
            name = sumNames[i]
            aNames[bound.a] = name.upper() if bound.aMirror else name
            bNames[bound.b] = name.upper() if bound.bMirror else name

        aNames = ''.join(aNames)
        bNames = ''.join(bNames)
        cNames = ''.join(cNames)
        dNames = ''.join(dNames)
        sumNames = ''.join(sumNames)

        return (aNames, bNames, cNames, dNames, sumNames)

    @property
    def operationIdentifier(self):
        (aNames, bNames, cNames, dNames, sumNames) = self.indexNames

        aOp = 'C' if self.aConjugate else ''
        bOp = 'C' if self.bConjugate else ''

        return '_'.join(['Contraction', sumNames,
                         'A' + aNames + aOp,
                         'B' + bNames + bOp,
                         'C' + cNames,
                         'D' + dNames])

    def placeholderStr(self, includeBatch=False, includeOperation=False, includeType=False):
        ret = ""
        if includeOperation:
            ret = self.operationIdentifier
            if not self.useBeta:
                ret += "_Beta0"
            ret += "_StridedBatched{}".format(int(self.stridedBatched))
        if includeType:
            ret += "_Type_{}{}".format(DataType(self.aType).toChar(), DataType(self.cType).toChar())
            if self.highPrecisionAccumulate:
                ret += "_HPA"

        return ret

    def predicates(self, includeBatch=False, includeOperation=False, includeType=False):
        predicates = []

        #if includeBatch and not self.batched:
        #    predicates.append(ProblemPredicate("BatchSizeEqual", index=0, value=1))

        if includeOperation:
            predicates.append(ProblemPredicate("OperationIdentifierEqual", value=self.operationIdentifier))
            if not self.useBeta:
                predicates.append(ProblemPredicate("BetaZero"))
            predicates.append(ProblemPredicate("BiasDataTypeWhiteList", value=self.biasDataTypeWhiteList))
            predicates.append(ProblemPredicate("BiasSrcWhiteList", value=self.biasSrcWhiteList))
            if self.activationType == 'all':
                exportType = ActivationType.Export.GRADONLY if self.useGradient else ActivationType.Export.NORMAL
                enumList = [actEnum.capitalize() for actEnum in ActivationType.getEnumStrList(self.activationComputeDataType, exportType=exportType)]
                predicates.append(ProblemPredicate("ActivationEnumWhiteList", value=enumList))
            # predicates.append(ProblemPredicate("UseScaleDVec", value=self.useScaleDVec))
            # predicates.append(ProblemPredicate("GroupedGemm", value=self.groupedGemm))

        if includeType:
            predicates.append(ProblemPredicate("TypesEqual", value=(self.aType, self.bType, self.cType, self.dType)))
            predicates.append(ProblemPredicate("HighPrecisionAccumulate", value=self.highPrecisionAccumulate))
            predicates.append(ProblemPredicate("Activation", value=self.activationType))
            predicates.append(ProblemPredicate("ActivationComputeType", value=self.activationComputeDataType))
            predicates.append(ProblemPredicate("ActivationNoGuard", value=self.activationNoGuard))
            predicates.append(ProblemPredicate("UseGradient", value=self.useGradient))
            predicates.append(ProblemPredicate("UseBias", value=self.useBias))
            predicates.append(ProblemPredicate("UseE", value=self.useE))
            predicates.append(ProblemPredicate("StridedBatched", value=self.stridedBatched))
            predicates.append(ProblemPredicate("GroupedGemm", value=self.groupedGemm))
            predicates.append(ProblemPredicate("UseScaleDVec", value=self.useScaleDVec))
            predicates.append(ProblemPredicate("SparseA", value=self.sparseA))
            predicates.append(ProblemPredicate("F32XdlMathOp", value=self.f32XdlMathOp))
            predicates.append(ProblemPredicate("SupportDeviceUserArguments", value=self.supportDeviceUserArguments))

        return predicates

def extractDimPredicate(cls, key, value, predicateName):
    """
    Extract the predicate for AssertStrideEqual*
    Value is a dictionary
    """
    predicates = []
    for pos,val in value.items():
        if val != -1:
            predicates.append(cls(predicateName, index=pos, value=val))
    if len(predicates) == 1:
        return predicates[0]
    elif len(predicates) > 1:
        return cls.And(predicates)

class ProblemPredicate(Properties.Predicate):
    @classmethod
    def FromOriginalKeyPair(cls, pair):
        (key, value) = pair
        if key.endswith('Multiple'):
            if value == 1:
                return None

            if key == "AssertFree0ElementMultiple":
                tag = "Free0SizeMultiple"
                index = 0
            elif key == "AssertFree1ElementMultiple":
                tag = "Free1SizeMultiple"
                index = 0
            elif key == "AssertSummationElementMultiple":
                tag = "BoundSizeMultiple"
                index = -1
            else:
                raise RuntimeError("Unknown Multiple Value: {}".format(key))

            return cls(tag, index=index, value=value)

        if key == "WorkspaceCheck" and (not all(val == 0 for val in value)):
            return cls("WorkspaceCheck", index=0, value=value)

        if key.startswith('Assert'):
            raise RuntimeError("Unknown assertion key: {}".format(key))

        if key == "Fp16AltImpl":
            return cls("Fp16AltImpl") if value != False else None

    @classmethod
    def CompoundPredicates(cls, state, problemType):
        rv = []

        if not problemType.aType.isInt8x4():
            # calculate the minimum supported free dimension size
            TLUA = state['ProblemType']['TLUA']
            TLUB = state['ProblemType']['TLUB']
            minFree0 = state['GlobalReadVectorWidthA'] if TLUA else 1
            minFree1 = state['GlobalReadVectorWidthB'] if TLUB else 1
            minFree1 = 0 if state['ProblemType']['GroupedGemm'] else minFree0
            rv += [cls('LeadingFree0SizesGreaterOrEqual', value=minFree0)]
            rv += [cls('LeadingFree1SizesGreaterOrEqual', value=minFree1)]

        if len(state["PackedC0IndicesX"]) > 1:
          rv += [cls("CDStridesEqual")]

        if "KernelLanguage" in state:
            rv += [cls("KernelLanguageCompatible", value=state["KernelLanguage"])]

        if ('GlobalSplitU' in state) and (state['GlobalSplitU'] > 1):
            if ('_GlobalAccumulation' not in state) or (state['_GlobalAccumulation'] != 'MultipleBuffer'):
                rv += [cls("DeterministicMode", value = False)]

        # if bufferload is performed, we output some predication info for host side,
        # to prevent from some extremely large problems from launching and causing bufferload offset limit < 2^32
        # thoses cases will not satisfy the assertion thus won't use the kernel.
        # See Common.py for more details, we will need four values:
        # TODO - haven't been fully tested for FP16 and BF, need to verify the false-positive
        if 'BufferLoad' in state and state['BufferLoad'] == True:
            TLUA = state['ProblemType']['TLUA']
            TLUB = state['ProblemType']['TLUB']
            MayShiftA = TLUA and state['AssertFree0ElementMultiple'] < state['GlobalReadVectorWidthA']
            MayShiftB = TLUB and state['AssertFree1ElementMultiple'] < state['GlobalReadVectorWidthB']
            subrv={}
            subrv['ShiftPtrElemB'] = state['GlobalReadVectorWidthB'] if MayShiftB else 0
            subrv['ShiftPtrElemA'] = state['GlobalReadVectorWidthA'] if MayShiftA else 0
            subrv['DUorMT1'] = state['DepthU'] if TLUB else state['MacroTile1']
            subrv['DUorMT0'] = state['DepthU'] if TLUA else state['MacroTile0']
            # value is also a dict for better readibility, client side need to handel the serialization
            rv += [cls('BufferLoadOffsetLimitCheck', value=subrv)]

        # When doing globol write, may need to load matrix C if beta !=0
        if 'BufferLoad' in state and state['BufferLoad'] == True:
            rv += [cls('BufferLoadOffsetLimitCheck_Beta', value=state['MacroTile1'])]

        # similiar check is applied for bufferstore,
        # for bufferstore offset, test if the bot-right offset < 2^32,
        # it should be StrideA*MT1, so we need to output MT1 and use the StrideA of problem in host-side for predication
        if 'BufferStore' in state and state['BufferStore'] == True:
            rv += [cls('BufferStoreOffsetLimitCheck', value=state['MacroTile1'])]

        if '_GlobalAccumulation' in state and state['_GlobalAccumulation'] != None:
            value = globalParameters['MinKForGSU'] * state['GlobalSplitU']
            rv += [cls('GlobalSplitUCheckMinK', value=value)]

        return rv

    @classmethod
    def FromOriginalState(cls, d, problemType, morePreds=[]):
        problemTypePreds = problemType.predicates(True, True, True)
        compoundPreds = cls.CompoundPredicates(d, problemType)
        extraPreds = problemTypePreds + compoundPreds + morePreds

        predicates = [p for p in map(cls.FromOriginalKeyPair, d.items()) if p is not None] + extraPreds
        return cls.And(predicates)

class SizeMapping:
    StateKeys = ['workGroup',
                 'macroTile',
                 'threadTile',
                 'depthU',
                 'staggerU',
                 'globalSplitU',
                 'staggerStrideShift',
                 'workGroupMapping',
                 'packBatchDims',
                 'magicDivAlg',
                 'sourceKernel',
                 'globalAccumulation',
                 'workspaceSizePerElemC',
                 'workspaceSizePerElemBias',
                 'activationFused'
                 ]

    @classmethod
    def FromOriginalState(cls, d):
        globalAccum = 0
        if d['_GlobalAccumulation'] == 'SingleBuffer':
            globalAccum = 1
        if d['_GlobalAccumulation'] == 'MultipleBuffer':
            globalAccum = 2
        return cls(workGroup                = d['WorkGroup'],
                   macroTile                = cls.ReadOriginalMacroTile(d),
                   threadTile               = d['ThreadTile'],
                   workGroupMapping         = d['WorkGroupMapping'],
                   staggerU                 = d['StaggerU'] if 'StaggerU' in d else 0,
                   depthU                   = d['DepthU'],
                   globalSplitU             = d['GlobalSplitU'],
                   staggerStrideShift       = d['_staggerStrideShift'] if '_staggerStrideShift' in d else 0,
                   packBatchDims            = 0,
                   magicDivAlg              = d.get('MagicDivAlg', 1),
                   sourceKernel             = d['KernelLanguage'] == 'Source',
                   globalAccumulation       = globalAccum,
                   workspaceSizePerElemC    = d['_WorkspaceSizePerElemC'],
                   workspaceSizePerElemBias = d['_WorkspaceSizePerElemBias'],
                   activationFused          = d['ActivationFused']
                   )

    @classmethod
    def ReadOriginalMacroTile(cls, d):
        rv = [1,1,1]
        rv[0] = d['MacroTile0']
        rv[1] = d['MacroTile1']
        return rv

    def __init__(self, **kwargs):
        for (key, value) in list(kwargs.items()):
            setattr(self, key, value)

class Solution:
    StateKeys = ['name',
                'problemType',
                'hardwarePredicate',
                'problemPredicate',
                'sizeMapping',
                'debugKernel',
                'libraryLogicIndex',
                'index',
                'ideals',
                'linearModel']
    HiddenKeys = ['originalSolution']

    @classmethod
    def FromSolutionStruct(cls, solution):
        return cls.FromOriginalState(solution._state)

    @classmethod
    def FromOriginalState(cls, d, deviceInfo=None):
        rv = cls()


        if 'SolutionNameMin' in d:
            rv.name = d['SolutionNameMin']

        rv.problemType = ProblemType.FromOriginalState(d['ProblemType'])

        rv.problemPredicate = ProblemPredicate.FromOriginalState(d, rv.problemType)

        if 'DebugKernel' in d:
            rv.debugKernel = d['DebugKernel']

        if 'SolutionIndex' in d:
            rv.index = d['SolutionIndex']

        info = cls.ReadOriginalInfo(d)
        rv.libraryLogicIndex = int(info.get("SolutionIndex", -1))

        rv.sizeMapping = SizeMapping.FromOriginalState(d)
        if 'Ideals' in d:
            rv.ideals = d['Ideals']
        else:
            rv.ideals = {}

        if 'LinearModel' in d:
            rv.linearModel = d['LinearModel']
        else:
            rv.linearModel = {}

        if 'ISA' not in d:
            if d['KernelLanguage'] == 'Assembly':
                d['ISA'] = Common.gfxArch(deviceInfo[1])
            else:
                d['ISA'] = [0,0,0]

        if 'CUCount' not in d:
            d['CUCount'] = None

        rv.hardwarePredicate = Hardware.HardwarePredicate.FromHardware(d['ISA'], d['CUCount'])
        rv.originalSolution = OriginalSolution(d)

        return rv

    @classmethod
    def ReadOriginalInfo(cls, d):
        return dict([(key, str(value)) for (key, value) in list(d.items()) if key != 'ProblemType'])

    def __init__(self, **kwargs):
        self.name = None
        self.problemType = None
        self.hardwarePredicate = Hardware.HardwarePredicate('TruePred')
        self.problemPredicate = ProblemPredicate('TruePred')
        self.sizeMapping = None
        self.debugKernel = False
        self.libraryLogicIndex = {}
        self.index = None
        self.ideals = {}

        for key, value in kwargs:
            if key not in Solution.StateKeys and key not in Solution.HiddenKeys:
                raise KeyError("{0} is not a property of Solution.".format(key))

            setattr(self, key, value)
