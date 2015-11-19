#
# THIS CODE AND INFORMATION ARE PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EITHER EXPRESSED OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED WARRANTIES OF MERCHANTABILITY AND/OR FITNESS
# FOR A PARTICULAR PURPOSE. THIS CODE AND INFORMATION ARE NOT SUPPORTED BY XEBIALABS.
#

import codecs
import re
import sys

from . import constants
from .escprober import EscCharSetProber  # ISO-2122, etc.
from .latin1prober import Latin1Prober  # windows-1252
from .mbcsgroupprober import MBCSGroupProber  # multi-byte character sets
from .sbcsgroupprober import SBCSGroupProber  # single-byte character sets

MINIMUM_THRESHOLD = 0.20
ePureAscii = 0
eEscAscii = 1
eHighbyte = 2


class UniversalDetector:
    def __init__(self):
        self._highBitDetector = re.compile(b'[\x80-\xFF]')
        self._escDetector = re.compile(b'(\033|~{)')
        self._mEscCharSetProber = None
        self._mCharSetProbers = []
        self.reset()

    def reset(self):
        self.result = {'encoding': None, 'confidence': 0.0}
        self.done = False
        self._mStart = True
        self._mGotData = False
        self._mInputState = ePureAscii
        self._mLastChar = b''
        if self._mEscCharSetProber:
            self._mEscCharSetProber.reset()
        for prober in self._mCharSetProbers:
            prober.reset()

    def feed(self, aBuf):
        if self.done:
            return

        aLen = len(aBuf)
        if not aLen:
            return

        if not self._mGotData:
            # If the data starts with BOM, we know it is UTF
            if aBuf[:3] == codecs.BOM_UTF8:
                # EF BB BF  UTF-8 with BOM
                self.result = {'encoding': "UTF-8-SIG", 'confidence': 1.0}
            elif aBuf[:4] == codecs.BOM_UTF32_LE:
                # FF FE 00 00  UTF-32, little-endian BOM
                self.result = {'encoding': "UTF-32LE", 'confidence': 1.0}
            elif aBuf[:4] == codecs.BOM_UTF32_BE:
                # 00 00 FE FF  UTF-32, big-endian BOM
                self.result = {'encoding': "UTF-32BE", 'confidence': 1.0}
            elif aBuf[:4] == b'\xFE\xFF\x00\x00':
                # FE FF 00 00  UCS-4, unusual octet order BOM (3412)
                self.result = {
                    'encoding': "X-ISO-10646-UCS-4-3412",
                    'confidence': 1.0
                }
            elif aBuf[:4] == b'\x00\x00\xFF\xFE':
                # 00 00 FF FE  UCS-4, unusual octet order BOM (2143)
                self.result = {
                    'encoding': "X-ISO-10646-UCS-4-2143",
                    'confidence': 1.0
                }
            elif aBuf[:2] == codecs.BOM_LE:
                # FF FE  UTF-16, little endian BOM
                self.result = {'encoding': "UTF-16LE", 'confidence': 1.0}
            elif aBuf[:2] == codecs.BOM_BE:
                # FE FF  UTF-16, big endian BOM
                self.result = {'encoding': "UTF-16BE", 'confidence': 1.0}

        self._mGotData = True
        if self.result['encoding'] and (self.result['confidence'] > 0.0):
            self.done = True
            return

        if self._mInputState == ePureAscii:
            if self._highBitDetector.search(aBuf):
                self._mInputState = eHighbyte
            elif ((self._mInputState == ePureAscii) and
                    self._escDetector.search(self._mLastChar + aBuf)):
                self._mInputState = eEscAscii

        self._mLastChar = aBuf[-1:]

        if self._mInputState == eEscAscii:
            if not self._mEscCharSetProber:
                self._mEscCharSetProber = EscCharSetProber()
            if self._mEscCharSetProber.feed(aBuf) == constants.eFoundIt:
                self.result = {'encoding': self._mEscCharSetProber.get_charset_name(),
                               'confidence': self._mEscCharSetProber.get_confidence()}
                self.done = True
        elif self._mInputState == eHighbyte:
            if not self._mCharSetProbers:
                self._mCharSetProbers = [MBCSGroupProber(), SBCSGroupProber(),
                                         Latin1Prober()]
            for prober in self._mCharSetProbers:
                if prober.feed(aBuf) == constants.eFoundIt:
                    self.result = {'encoding': prober.get_charset_name(),
                                   'confidence': prober.get_confidence()}
                    self.done = True
                    break

    def close(self):
        if self.done:
            return
        if not self._mGotData:
            if constants._debug:
                sys.stderr.write('no data received!\n')
            return
        self.done = True

        if self._mInputState == ePureAscii:
            self.result = {'encoding': 'ascii', 'confidence': 1.0}
            return self.result

        if self._mInputState == eHighbyte:
            proberConfidence = None
            maxProberConfidence = 0.0
            maxProber = None
            for prober in self._mCharSetProbers:
                if not prober:
                    continue
                proberConfidence = prober.get_confidence()
                if proberConfidence > maxProberConfidence:
                    maxProberConfidence = proberConfidence
                    maxProber = prober
            if maxProber and (maxProberConfidence > MINIMUM_THRESHOLD):
                self.result = {'encoding': maxProber.get_charset_name(),
                               'confidence': maxProber.get_confidence()}
                return self.result

        if constants._debug:
            sys.stderr.write('no probers hit minimum threshhold\n')
            for prober in self._mCharSetProbers[0].mProbers:
                if not prober:
                    continue
                sys.stderr.write('%s confidence = %s\n' %
                                 (prober.get_charset_name(),
                                  prober.get_confidence()))
