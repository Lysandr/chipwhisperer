#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2013-2014, NewAE Technology Inc
# All rights reserved.
#
# Find this and more at newae.com - this file is part of the chipwhisperer
# project, http://www.assembla.com/spaces/chipwhisperer
#
#    This file is part of chipwhisperer.
#
#    chipwhisperer is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    chipwhisperer is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with chipwhisperer.  If not, see <http://www.gnu.org/licenses/>.
#=================================================

import random
import time

import chipwhisperer.common.utils.util as util
from chipwhisperer.common.api.config_parameter import ConfigParameter

class AcquisitionController():
    class Signals:
        def __init__(self):
            self.traceDone = util.Signal()
            self.captureDone = util.Signal()
            self.newTextResponse = util.Signal()

    def __init__(self, scope, target=None, writer=None, auxList=None, keyTextPattern=None):
        self.target = target
        self.scope = scope
        self.writer = writer
        self.auxList = auxList
        self.running = False
        self.setKeyTextPattern(keyTextPattern)
        self.signals = AcquisitionController.Signals()
        keyTextPattern.setTarget(target)

        self.maxtraces = 1

        if self.auxList is not None:
            for aux in auxList:
                aux.captureInit()

    def setKeyTextPattern(self, pat):
        self._keyTextPattern = pat
        if pat:
            self._keyTextPattern.initPair()

    def TargetDoTrace(self, plaintext, key=None):
        if self.target is None or self.target.getName()=="None":
            return []

        if key:
            self.target.loadEncryptionKey(key)
        self.target.loadInput(plaintext)
        self.target.go()

        timeout = 50
        while self.target.isDone() == False and timeout:
            timeout -= 1
            time.sleep(0.01)
            
        if timeout == 0:
            print "WARNING: Target timeout"

        # print "DEBUG: Target go()"

        resp = self.target.readOutput()
        # print "DEBUG: Target readOutput()"

        # print "pt:",
        # for i in plaintext:
        #    print " %02X"%i,
        # print ""

        # print "sc:",
        # for i in resp:
        #    print " %02X"%i,
        # print ""

        self.signals.newTextResponse.emit(self.key, plaintext, resp, self.target.getExpected())

        return resp

    def doSingleReading(self, update=True, N=None):
        # Set mode
        if self.auxList is not None:
            for aux in self.auxList:
                aux.traceArm()

        if self.scope is not None:
            self.scope.arm()

        if self.auxList is not None:
            for aux in self.auxList:
                aux.traceArmPost()

        if self.target is not None:
            # Get key / plaintext now
            data = self._keyTextPattern.newPair()
            self.key = data[0]
            self.textin = data[1]

            self.target.reinit()
            self.target.setModeEncrypt()
            self.target.loadEncryptionKey(self.key)
            # Load input, start encryption, get output. Key was set already, don't resend
            self.textout = self.TargetDoTrace(self.textin, key=None)
        else:
            self.textout = [0]

        # Get ADC reading
        if self.scope is not None:
            try:
                if self.scope.capture(update, N) == True:
#                if self.scope.capture(update, N, waitingCallback=QApplication.processEvents) == True:
                    print "Timeout"
                    return False
            except IOError, e:
                print "IOError: %s" % str(e)
                return False

        if self.auxList is not None:
            for aux in self.auxList:
                aux.traceDone()

        return True

    def setMaxtraces(self, maxtraces):
        self.maxtraces = maxtraces

    def abortCapture(self, doAbort=True):
        if doAbort:
            self.running = False

    def doReadings(self, addToList=None):
        self.running = True

        self._keyTextPattern.initPair()
        data = self._keyTextPattern.newPair()
        self.key = data[0]
        self.textin = data[1]

        if self.writer is not None:
            self.writer.prepareDisk()
            self.writer.setKnownKey(self.key)

        # TODO, what should this call be??
        if self.auxList is not None:
            for aux in self.auxList:
                aux.traceArm()

        self.currentTrace = 0

        while (self.currentTrace < self.maxtraces) and self.running:
            if self.doSingleReading(True, None) == True:
                if self.writer is not None:
                    self.writer.addTrace(self.scope.datapoints, self.textin, self.textout, self.key)
                self.signals.traceDone.emit()
                self.currentTrace = self.currentTrace + 1

        if self.auxList is not None:
            for aux in self.auxList:
                aux.captureComplete()

        if self.writer is not None:
            # Don't clear trace as we re-use the buffer
            self.writer.closeAll(clearTrace=False)

        if addToList is not None:
            if self.writer is not None:
                addToList.append(self.writer)

        self.signals.captureDone.emit(self.running)
        self.running = False

class AcqKeyTextPattern_Base(object):
    def __init__(self, target=None):
        self.params = ConfigParameter.create_extended(self, name='Key/Text Pattern', type='group', children=self.setupParams())
        self._target = target
        self._initPattern()

    def setTarget(self, target):
        self._target = target
        self._initPattern()

    def keyLen(self):
        if self._target:
            return self._target.keyLen()
        else:
            return 16

    def validateKey(self):
        if self._target:
            if len(self._key) != self._target.keyLen():
                raise IOError("Key Length Wrong for Given Target, %d != %d" % (self._target.keyLen(), len(self.key)))

            self._key = self._target.checkEncryptionKey(self._key)

    def setupParams(self):
        return [{'name':'Do Something', 'type':'bool'},]

    def paramList(self):
        return [self.params]

    def _initPattern(self):
        """Perform any extra init stuff required. Called at the end of main init() & when target changed."""
        pass

    def setInitialKey(self, initialKey, binaryKey=False):
        pass

    def setInitialText(self, initialText, binaryText=False):
        pass

    def initPair(self):
        """Called before a capture run, does not return anything"""
        raise AttributeError("This needs to be reimplemented")

    def newPair(self):
        """Called when a new encryption pair is requested"""
        raise AttributeError("This needs to be reimplemented")

class AcqKeyTextPattern_Basic(AcqKeyTextPattern_Base):
    def setupParams(self):
        self._fixedPlain = False
        self._fixedKey = True

        basicParams = [
                      {'name':'Key', 'type':'list', 'values':['Random', 'Fixed'], 'value':'Fixed', 'set':self.setKeyType},
                      {'name':'Plaintext', 'type':'list', 'values':['Random', 'Fixed'], 'value':'Random', 'set':self.setPlainType},
                      {'name':'Fixed Encryption Key', 'key':'initkey', 'type':'str', 'set':self.setInitialKey},
                      {'name':'Fixed Plaintext Key', 'key':'inittext', 'type':'str', 'set':self.setInitialText},
                  ]
        return basicParams

    def setKeyType(self, t):
        if t == 'Fixed':
            self._fixedKey = True
        elif t == 'Random':
            self._fixedKey = False
        else:
            raise ValueError("Invalid value for Key Type: %s" % t)

    def setPlainType(self, t):
        if t == 'Fixed':
            self._fixedPlain = True
        elif t == 'Random':
            self._fixedPlain = False
        else:
            raise ValueError("Invalid value for Text Type: %s" % t)

    def _initPattern(self):
        self.setInitialKey('2b 7e 15 16 28 ae d2 a6 ab f7 15 88 09 cf 4f 3c')
        self.setInitialText('00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F')

    def setInitialKey(self, initialKey, binaryKey=False):
        if initialKey:
            if binaryKey:
                keyStr = ''
                for s in initialKey:
                    keyStr += '%02x ' % s
                self._key = bytearray(initialKey)
            else:
                keyStr = initialKey
                self._key = util.hexStrToByteArray(initialKey)

            self.initkey = keyStr

    def setInitialText(self, initialText, binaryText=False):
        if initialText:
            if binaryText:
                textStr = ''
                for s in initialText:
                    textStr += '%02x ' % s
                self._textin = bytearray(initialText)
            else:
                textStr = initialText
                self._textin = util.hexStrToByteArray(initialText)

            self.inittext = textStr

    def initPair(self):
        self._initPattern()

    def newPair(self):
        if self._fixedKey is False:
            self._key = bytearray(self.keyLen())
            for i in range(0, self.keyLen()):
                self._key[i] = random.randint(0, 255)

        if self._fixedPlain is False:
            self._textin = bytearray(16)
            for i in range(0, 16):
                self._textin[i] = random.randint(0, 255)

        # Check key works with target
        self.validateKey()

        return (self._key, self._textin)

class AcqKeyTextPattern_CRITTest(AcqKeyTextPattern_Base):
    def setupParams(self):
        self._fixedPlain = False
        self._fixedKey = True
        basicParams = [
                      # {'name':'Key', 'type':'list', 'values':['Random', 'Fixed'], 'value':'Fixed', 'set':self.setKeyType},
                  ]
        return basicParams

    def _initPattern(self):
        pass

    def initPair(self):
        if self.keyLen() == 16:
            self._key = util.hexStrToByteArray("01 23 45 67 89 ab cd ef 12 34 56 78 9a bc de f0")
        elif self.keyLen() == 24:
            self._key = util.hexStrToByteArray("01 23 45 67 89 ab cd ef 12 34 56 78 9a bc de f0 23 45 67 89 ab cd ef 01")
        elif self.keyLen() == 32:
            self._key = util.hexStrToByteArray("01 23 45 67 89 ab cd ef 12 34 56 78 9a bc de f0 23 45 67 89 ab cd ef 01 34 56 78 9a bc de f0 12")
        else:
            raise ValueError("Invalid key length: %d bytes" % self.keyLen())

        self._textin1 = util.hexStrToByteArray("00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")

        if self.keyLen() == 16:
            self._textin2 = util.hexStrToByteArray("da 39 a3 ee 5e 6b 4b 0d 32 55 bf ef 95 60 18 90")
        elif self.keyLen() == 24:
            self._textin2 = util.hexStrToByteArray("da 39 a3 ee 5e 6b 4b 0d 32 55 bf ef 95 60 18 88")
        elif self.keyLen() == 32:
            self._textin2 = util.hexStrToByteArray("da 39 a3 ee 5e 6b 4b 0d 32 55 bf ef 95 60 18 95")
        else:
            raise ValueError("Invalid key length: %d bytes" % self.keyLen())

        self.group1 = True

    def newPair(self):
        if self.group1:
            self.group1 = False
            self._textin = self._textin1

            try:
                from Crypto.Cipher import AES
                cipher = AES.new(str(self._key), AES.MODE_ECB)
                self._textin1 = bytearray(cipher.encrypt(str(self._textin1)))
            except ImportError:
                print "No AES Module, Using rand() instead!"
                self._textin1 = bytearray(16)
                for i in range(0, 16):
                    self._textin1[i] = random.randint(0, 255)

        else:
            self.group1 = True
            self._textin = self._textin2

        # Check key works with target
        self.validateKey()

        return (self._key, self._textin)
