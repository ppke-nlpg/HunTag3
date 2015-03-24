#!/usr/bin/python3
# -*- coding: utf-8, vim: expandtab:ts=4 -*-

from collections import defaultdict
import argparse
from os.path import isdir, join
import sys
import os
import numpy as np

from feature import Feature
from trainer import Trainer
from tagger import Tagger
from bigram import TransModel


def mainBigramTrain(options, inputStream=sys.stdin):
    bigramModel = TransModel(options['tagField'], lmw=options['lmw'])
    # It's possible to train multiple times incrementally...
    bigramModel.train(inputStream)
    # Close training, compute probabilities
    bigramModel.count()
    bigramModel.writeToFile(options['bigramModelFileName'])


def mainTrain(featureSet, options, inputStream=sys.stdin):
    trainer = Trainer(featureSet, options)

    if 'inFeatFile' in options and options['inFeatFile']:
        # Use with featurized input
        trainer.getEventsFromFile(options['inFeatFile'])
    else:
        # Use with raw input
        trainer.getEvents(inputStream)

    if options['task'] == 'most-informative-features':
        trainer.mostInformativeFeatures()
    elif 'toCRFsuite' in options and options['toCRFsuite']:
        trainer.cutoffFeats()
        trainer.toCRFsuite()
    else:
        trainer.cutoffFeats()
        trainer.train()
        trainer.save()


def mainTag(featureSet, options, inputStream=sys.stdin):
    tagger = Tagger(featureSet, options)
    if 'inFeatFile' in options and options['inFeatFile']:
        # Tag a featurized file to to STDOUT
        taggerFunc = lambda: tagger.tagFeatures(options['inFeatFile'])
        writerFunc = lambda s, c: writeSentence(s, comment=c)
    elif 'ioDirs' in options and options['ioDirs']:
        # Tag all files in a directory file to to fileName.tagged
        taggerFunc = lambda: tagger.tagDir(options['ioDirs'][0])
        writerFunc = lambda s, c: writeSentence(s, out=open(join(options['ioDirs'][1],
            '{0}.tagged'.format(c)), 'a', encoding='UTF-8'))
    elif 'toCRFsuite' in options and options['toCRFsuite']:
        # Make CRFsuite format to STDOUT for tagging
        taggerFunc = lambda: tagger.toCRFsuite(inputStream)
        writerFunc = lambda s, c: None
    elif 'printWeights' in options and options['printWeights']:
        # Print MaxEnt weights to STDOUT
        taggerFunc = lambda: tagger.printWeights(options['printWeights'])
        writerFunc = lambda s, c: None
    else:
        # Tag STDIN to STDOUT
        taggerFunc = lambda: tagger.tagCorp(inputStream)
        writerFunc = lambda s, c: writeSentence(s, comment=c)

    for sen, other in taggerFunc():
        writerFunc(sen, other)


def writeSentence(sen, out=sys.stdout, comment=None):
    if comment:
        out.write('{0}\n'.format(comment))
    for tok in sen:
        out.write('{0}\n'.format('\t'.join(tok)))
    out.write('\n')


def getFeatureSet(cfgFile):
    features = {}
    optsByFeature = defaultdict(dict)
    defaultRadius = -1
    defaultCutoff = 1
    for line in open(cfgFile, encoding='UTF-8'):
        line = line.strip()
        if len(line) == 0 or line[0] == '#':
            continue
        feature = line.split()
        if feature[0] == 'let':
            featName, key, value = feature[1:4]
            optsByFeature[featName][key] = value
            continue
        if feature[0] == '!defaultRadius':
            defaultRadius = int(feature[1])
            continue
        if feature[0] == '!defaultCutoff':
            defaultCutoff = int(feature[1])
            continue

        feaType, name, actionName = feature[:3]
        fields = [int(field) for field in feature[3].split(',')]
        if len(feature) > 4:
            radius = int(feature[4])
        else:
            radius = defaultRadius
        cutoff = defaultCutoff
        options = optsByFeature[name]
        feat = Feature(feaType, name, actionName, fields, radius, cutoff, options)
        features[name] = feat

    return features


def validDir(inputDir):
    if not isdir(inputDir):
        raise argparse.ArgumentTypeError('"{0}" must be a directory!'.format(inputDir))
    outDir = '{0}_out'.format(inputDir)
    os.mkdir(outDir)
    return inputDir, outDir


def parseArgs():
    parser = argparse.ArgumentParser()

    parser.add_argument('task', choices=['bigram-train', 'most-informative-features', 'train', 'tag'],
                        help='avaliable tasks: bigram-train, most-informative-features, train, tag')

    parser.add_argument('-c', '--config-file', dest='cfgFile',
                        help='read feature configuration from FILE',
                        metavar='FILE')

    parser.add_argument('-m', '--model', dest='modelName',
                        help='name of (bigram) model to be read/written',
                        metavar='NAME')

    parser.add_argument('--model-ext', dest='modelExt', default='.model',
                        help='extension of model to be read/written',
                        metavar='EXT')

    parser.add_argument('--bigram-model-ext', dest='bigramModelExt', default='.bigram',
                        help='extension of bigram model file to be read/written',
                        metavar='EXT')

    parser.add_argument('--feat-num-ext', dest='featureNumbersExt', default='.featureNumbers',
                        help='extension of feature numbers file to be read/written',
                        metavar='EXT')

    parser.add_argument('--label-num-ext', dest='labelNumbersExt', default='.labelNumbers',
                        help='extension of label numbers file to be read/written',
                        metavar='EXT')

    parser.add_argument('-l', '--language-model-weight', dest='lmw',
                        type=float, default=1,
                        help='set relative weight of the language model to L',
                        metavar='L')

    parser.add_argument('-o', '--cutoff', dest='cutoff', type=int, default=2,
                        help='set global cutoff to C',
                        metavar='C')

    parser.add_argument('-p', '--parameters', dest='trainParams',
                        help='pass PARAMS to trainer',
                        metavar='PARAMS')

    parser.add_argument('-u', '--used-feats', dest='usedFeats',
                        help='limit used features to those in FILE',
                        metavar='FILE')

    group = parser.add_mutually_exclusive_group()

    group.add_argument('-d', '--input-dir', dest='ioDirs', type=validDir,
                       help='process all files in DIR (instead of stdin)',
                       metavar='DIR')

    group.add_argument('-i', '--input-feature-file', dest='inFeatFileName',
                       help='use training events in FILE (already featurized input, see --toCRFsuite)',
                       metavar='FILE')

    parser.add_argument('-f', '--feature-file', dest='outFeatFileName',
                        help='write training events to FILE (deprecated, use --toCRFsuite instead)',
                        metavar='FILE')

    parser.add_argument('-t', '--tag-field', dest='tagField', type=int, default=-1,
                        help='specify FIELD containing the labels to build models from',
                        metavar='FIELD')

    parser.add_argument('--toCRFsuite', dest='toCRFsuite', action='store_true', default=False,
                        help='convert input to CRFsuite format to STDOUT')

    parser.add_argument('--printWeights', dest='printWeights', type=int,
                        help='print model weights instead of tagging')

    return parser.parse_args()


def main():
    options = parseArgs()
    if options.outFeatFileName:
        print('Error: Argument --feature-file is deprecated! Use --toCRFsuite instead!',
              file=sys.stderr, flush=True)
        sys.exit(1)

    if not options.modelName:
        print('Error: Model name must be specified! Please see --help!', file=sys.stderr, flush=True)
        sys.exit(1)
    options.modelFileName = '{0}{1}'.format(options.modelName, options.modelExt)
    options.bigramModelFileName = '{0}{1}'.format(options.modelName, options.bigramModelExt)
    options.featCounterFileName = '{0}{1}'.format(options.modelName, options.featureNumbersExt)
    options.labelCounterFileName = '{0}{1}'.format(options.modelName, options.labelNumbersExt)

    # Data sizes across the program (training and tagging). Check manuals for other sizes
    options.dataSizes = {'rows': 'Q', 'rowsNP': np.uint64,       # Really big...
                         'cols': 'Q', 'colsNP': np.uint64,       # ...enough for indices
                         'data': 'B', 'dataNP': np.uint8,        # Currently data = {0, 1}
                         'labels': 'B', 'labelsNP': np.uint16,   # Currently labels > 256...
                         'sentEnd': 'Q', 'sentEndNP': np.uint64  # Sentence Ends in rowIndex
                        }                                        # ...for safety

    optionsDict = vars(options)
    if optionsDict['task'] == 'bigram-train':
        mainBigramTrain(optionsDict)
    elif optionsDict['task'] == 'train' or optionsDict['task'] == 'most-informative-features':
        featureSet = getFeatureSet(optionsDict['cfgFile'])
        mainTrain(featureSet, optionsDict)
    elif optionsDict['task'] == 'tag':
        if optionsDict['inFeatFileName']:
            featureSet = None
            optionsDict['inFeatFile'] = open(optionsDict['inFeatFileName'], encoding='UTF-8')
        else:
            featureSet = getFeatureSet(optionsDict['cfgFile'])
        mainTag(featureSet, optionsDict)
    else:
        print('Error: Task name must be specified! Please see --help!', file=sys.stderr, flush=True)
        sys.exit(1)

if __name__ == '__main__':
    main()
