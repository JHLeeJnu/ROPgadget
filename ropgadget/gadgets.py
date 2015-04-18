## -*- coding: utf-8 -*-
##
##  Jonathan Salwan - 2014-05-12 - ROPgadget tool
## 
##  http://twitter.com/JonathanSalwan
##  http://shell-storm.org/project/ROPgadget/
## 
##  This program is free software: you can redistribute it and/or modify
##  it under the terms of the GNU General Public License as published by
##  the Free Software  Foundation, either  version 3 of  the License, or
##  (at your option) any later version.

import re
from   capstone import *

class Gadgets:
    def __init__(self, binary, options, offset):
        self.__binary  = binary
        self.__options = options
        self.__offset  = offset


    def __checkInstructionBlackListedX86(self, insts):
        bl = ["db", "int3"]
        for inst in insts:
            for b in bl:
                if inst.split(" ")[0] == b:
                    return True 
        return False

    def __checkMultiBr(self, insts, br):
        count = 0
        for inst in insts:
            if inst.split()[0] in br:
                count += 1
        return count

    def __passCleanX86(self, gadgets, multibr=False):
        new = []
        br = ["ret", "int", "sysenter", "jmp", "call"]
        for gadget in gadgets:
            insts = gadget["gadget"].split(" ; ")
            if len(insts) == 1 and insts[0].split(" ")[0] not in br:
                continue
            if insts[-1].split(" ")[0] not in br:
                continue
            if self.__checkInstructionBlackListedX86(insts):
                continue
            if not multibr and self.__checkMultiBr(insts, br) > 1:
                continue
            if len([m.start() for m in re.finditer("ret", gadget["gadget"])]) > 1:
                continue
            new += [gadget]
        return new

    def __gadgetsFinding(self, section, gadgets):

        C_OP    = 0
        C_SIZE  = 1
        C_ALIGN = 2
        C_ARCH  = 3
        C_MODE  = 4

        ret = []
        for gad in gadgets:
            allRefRet = [m.start() for m in re.finditer(gad[C_OP], section["opcodes"])]
            for ref in allRefRet:
                for i in range(self.__options.depth):
                    md = Cs(gad[C_ARCH], gad[C_MODE])
                    decodes = md.disasm(section["opcodes"][ref-(i*gad[C_ALIGN]):ref+gad[C_SIZE]], section["vaddr"]+ref)
                    gadget = ""
                    for decode in decodes:
                        gadget += (decode.mnemonic + " " + decode.op_str + " ; ").replace("  ", " ")
                    if len(gadget) > 0:
                        gadget = gadget[:-3]
                        if (section["vaddr"]+ref-(i*gad[C_ALIGN])) % gad[C_ALIGN] == 0:
                            off = self.__offset
                            ret += [{"vaddr" :  off+section["vaddr"]+ref-(i*gad[C_ALIGN]), "gadget" : gadget, "decodes" : decodes, "bytes": section["opcodes"][ref-(i*gad[C_ALIGN]):ref+gad[C_SIZE]]}]
        return ret

    def addROPGadgets(self, section):

        gadgetsX86   = [
                            [b"\xc3", 1, 1, self.__binary.getArch(), self.__binary.getArchMode()],               # ret
                            [b"\xc2[\x00-\xff]{2}", 3, 1, self.__binary.getArch(), self.__binary.getArchMode()]  # ret <imm>
                       ]
        gadgetsSparc = [
                            [b"\x81\xc3\xe0\x08", 4, 4, self.__binary.getArch(), CS_MODE_BIG_ENDIAN], # retl
                            [b"\x81\xc7\xe0\x08", 4, 4, self.__binary.getArch(), CS_MODE_BIG_ENDIAN], # ret
                            [b"\x81\xe8\x00\x00", 4, 4, self.__binary.getArch(), CS_MODE_BIG_ENDIAN]  # restore
                       ]
        gadgetsPPC   = [
                            [b"\x4e\x80\x00\x20", 4, 4, self.__binary.getArch(), self.__binary.getArchMode() + CS_MODE_BIG_ENDIAN] # blr
                       ]
        gadgetsARM64 = [
                            [b"[\x00\x20\x40\x60\x80\xa0\xc0\xe0][\x00-\x02]\x5f\xd6", 4, 4, self.__binary.getArch(), CS_MODE_ARM], # ret reg
                            [b"[\x00\x20\x40\x60\x80]\x03\x5f\xd6", 4, 4, self.__binary.getArch(), CS_MODE_ARM], # ret reg
                            [b"\xc0\x03\x5f\xd6", 4, 4, self.__binary.getArch(), CS_MODE_ARM] # ret
                       ]

        if   self.__binary.getArch() == CS_ARCH_X86:    gadgets = gadgetsX86
        elif self.__binary.getArch() == CS_ARCH_MIPS:   gadgets = []            # MIPS doesn't contains RET instruction set. Only JOP gadgets
        elif self.__binary.getArch() == CS_ARCH_PPC:    gadgets = gadgetsPPC
        elif self.__binary.getArch() == CS_ARCH_SPARC:  gadgets = gadgetsSparc
        elif self.__binary.getArch() == CS_ARCH_ARM:    gadgets = []            # ARM doesn't contains RET instruction set. Only JOP gadgets
        elif self.__binary.getArch() == CS_ARCH_ARM64:  gadgets = gadgetsARM64
        else:
            print("Gadgets().addROPGadgets() - Architecture not supported")
            return None

        return self.__gadgetsFinding(section, gadgets)

    def addJOPGadgets(self, section):

        gadgetsX86      = [
                               [b"\xff[\x20\x21\x22\x23\x26\x27]{1}", 2, 1, self.__binary.getArch(), self.__binary.getArchMode()], # jmp  [reg]
                               [b"\xff[\xe0\xe1\xe2\xe3\xe4\xe6\xe7]{1}", 2, 1, self.__binary.getArch(), self.__binary.getArchMode()], # jmp  [reg]
                               [b"\xff[\x10\x11\x12\x13\x16\x17]{1}", 2, 1, self.__binary.getArch(), self.__binary.getArchMode()], # jmp  [reg]
                               [b"\xff[\xd0\xd1\xd2\xd3\xd4\xd6\xd7]{1}", 2, 1, self.__binary.getArch(), self.__binary.getArchMode()], # call  [reg]
                               [b"\xff[\x14\x24]\x24", 3, 1, self.__binary.getArch(), self.__binary.getArchMode()],  # jmp/call dword ptr [esp]
                               [b"\xff[\x55\x65]\x00", 3, 1, self.__binary.getArch(), self.__binary.getArchMode()],  # jmp/call dword ptr [ebp]
                               [b"\xff[\xa0\xa1\xa2\xa3\xa6\xa7][\x00-\x0ff]{4}", 6, 1, self.__binary.getArch(), self.__binary.getArchMode()],  # jmp dword ptr [reg + 0xXXXXXXXX]
                               [b"\xff\xa4\x24[\x00-\x0ff]{4}", 7, 1, self.__binary.getArch(), self.__binary.getArchMode()],  # jmp dword ptr [esp + 0xXXXXXXXX]
                               [b"\xff[\x90\x91\x92\x93\x94\x96\x97][\x00-\x0ff]{4}", 6, 1, self.__binary.getArch(), self.__binary.getArchMode()]  # call dword ptr [reg + 0xXXXXXXXX]

                          ]
        gadgetsSparc    = [
                               [b"\x81\xc0[\x00\x40\x80\xc0]{1}\x00", 4, 4, self.__binary.getArch(), CS_MODE_BIG_ENDIAN]  # jmp %g[0-3]
                          ]
        gadgetsMIPS     = [
                               [b"\x09\xf8\x20\x03", 4, 4, self.__binary.getArch(), self.__binary.getArchMode()], # jrl $t9
                               [b"\x08\x00\x20\x03", 4, 4, self.__binary.getArch(), self.__binary.getArchMode()], # jr  $t9
                               [b"\x08\x00\xe0\x03", 4, 4, self.__binary.getArch(), self.__binary.getArchMode()]  # jr  $ra
                          ]
        gadgetsARMThumb = [
                               [b"[\x00\x08\x10\x18\x20\x28\x30\x38\x40\x48\x70]{1}\x47", 2, 2, self.__binary.getArch(), CS_MODE_THUMB], # bx   reg
                               [b"[\x80\x88\x90\x98\xa0\xa8\xb0\xb8\xc0\xc8\xf0]{1}\x47", 2, 2, self.__binary.getArch(), CS_MODE_THUMB], # blx  reg
                               [b"[\x00-\xff]{1}\xbd", 2, 2, self.__binary.getArch(), CS_MODE_THUMB]                                     # pop {,pc}
                          ]
        gadgetsARM      = [
                               [b"[\x10-\x19\x1e]{1}\xff\x2f\xe1", 4, 4, self.__binary.getArch(), CS_MODE_ARM],  # bx   reg
                               [b"[\x30-\x39\x3e]{1}\xff\x2f\xe1", 4, 4, self.__binary.getArch(), CS_MODE_ARM],  # blx  reg
                               [b"[\x00-\xff]{1}\x80\xbd\xe8", 4, 4, self.__binary.getArch(), CS_MODE_ARM]       # pop {,pc}
                          ]
        gadgetsARM64    = [
                               [b"[\x00\x20\x40\x60\x80\xa0\xc0\xe0]{1}[\x00\x02]{1}\x1f\xd6", 4, 4, self.__binary.getArch(), CS_MODE_ARM],     # br  reg
                               [b"[\x00\x20\x40\x60\x80\xa0\xc0\xe0]{1}[\x00\x02]{1}\x5C\x3f\xd6", 4, 4, self.__binary.getArch(), CS_MODE_ARM],  # blr reg
                               [b"[\x00\x20\x40\x60\x80]\x03\x1f\xd6", 4, 4, self.__binary.getArch(), CS_MODE_ARM],  # bl reg
                               [b"[\x00\x20\x40\x60\x80]\x03\x3f\xd6", 4, 4, self.__binary.getArch(), CS_MODE_ARM]  # blr reg
                          ]

        if   self.__binary.getArch() == CS_ARCH_X86:    gadgets = gadgetsX86
        elif self.__binary.getArch() == CS_ARCH_MIPS:   gadgets = gadgetsMIPS
        elif self.__binary.getArch() == CS_ARCH_PPC:    gadgets = [] # PPC architecture doesn't contains reg branch instruction
        elif self.__binary.getArch() == CS_ARCH_SPARC:  gadgets = gadgetsSparc
        elif self.__binary.getArch() == CS_ARCH_ARM64:  gadgets = gadgetsARM64
        elif self.__binary.getArch() == CS_ARCH_ARM:
            if self.__options.thumb or self.__options.rawMode == "thumb":
                gadgets = gadgetsARMThumb
            else:
                gadgets = gadgetsARM
        else:
            print("Gadgets().addJOPGadgets() - Architecture not supported")
            return None

        return self.__gadgetsFinding(section, gadgets)

    def addSYSGadgets(self, section):

        gadgetsX86      = [
                               [b"\xcd\x80", 2, 1, self.__binary.getArch(), self.__binary.getArchMode()], # int 0x80
                               [b"\x0f\x34", 2, 1, self.__binary.getArch(), self.__binary.getArchMode()], # sysenter
                               [b"\x0f\x05", 2, 1, self.__binary.getArch(), self.__binary.getArchMode()], # syscall
                          ]
        gadgetsARMThumb = [
                               [b"\x00-\xff]{1}\xef", 2, 2, self.__binary.getArch(), CS_MODE_THUMB], # svc
                          ]
        gadgetsARM      = [
                               [b"\x00-\xff]{3}\xef", 4, 4, self.__binary.getArch(), CS_MODE_ARM] # svc
                          ]
        gadgetsMIPS     = [
                               [b"\x0c\x00\x00\x00", 4, 4, self.__binary.getArch(), self.__binary.getArchMode()] # syscall
                          ]

        if   self.__binary.getArch() == CS_ARCH_X86:    gadgets = gadgetsX86
        elif self.__binary.getArch() == CS_ARCH_MIPS:   gadgets = gadgetsMIPS
        elif self.__binary.getArch() == CS_ARCH_PPC:    gadgets = [] # TODO (sc inst)
        elif self.__binary.getArch() == CS_ARCH_SPARC:  gadgets = [] # TODO (ta inst)
        elif self.__binary.getArch() == CS_ARCH_ARM64:  gadgets = [] # TODO
        elif self.__binary.getArch() == CS_ARCH_ARM:
            if self.__options.thumb or self.__options.rawMode == "thumb":
                gadgets = gadgetsARMThumb
            else:
                gadgets = gadgetsARM
        else:
            print("Gadgets().addSYSGadgets() - Architecture not supported")
            return None

        return self.__gadgetsFinding(section, gadgets)

    def passClean(self, gadgets, multibr):
        if   self.__binary.getArch() == CS_ARCH_X86:    return self.__passCleanX86(gadgets, multibr)
        elif self.__binary.getArch() == CS_ARCH_MIPS:   return gadgets 
        elif self.__binary.getArch() == CS_ARCH_PPC:    return gadgets
        elif self.__binary.getArch() == CS_ARCH_SPARC:  return gadgets
        elif self.__binary.getArch() == CS_ARCH_ARM:    return gadgets 
        elif self.__binary.getArch() == CS_ARCH_ARM64:  return gadgets
        else:
            print("Gadgets().passClean() - Architecture not supported")
            return None

