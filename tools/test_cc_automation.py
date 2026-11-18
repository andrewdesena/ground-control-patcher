#!/usr/bin/env python3
"""Exercise CC through installed input, player, writer and loader hooks."""
import json, struct, zlib
from pathlib import Path
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2
from fw_sandbox import Sandbox
from test_poly_live_record import bench,advance,RECORDERS,EVENT,LETTER
from test_poly_v119 import TRACKS,BANK,SIZE,OWNER,neutralize,install_fatfs,run,pattern_file,sidecar
ROOT=Path(__file__).resolve().parent.parent
BUNDLE=ROOT/json.loads((ROOT/'firmware/releases.json').read_text())['candidate']['bundle']
SYMS={k:int(v,16) for k,v in json.loads((ROOT/'firmware/cc-symbols.json').read_text()).items()}
CC=0x1000B530;SNAP=0x1000BB60;OWN=0x1000BD80;VALID=0x1000BD8C

def seed(sb,slot,payload=None,letter=LETTER):
 sb.w(SNAP,b'\0'*540);sb.w(VALID,struct.pack('<I',int(payload is not None)))
 if payload is not None:sb.w(SNAP+8,payload)
 # Enter the real publication trampoline; a zero note flag must clear automation.
 from unicorn.arm_const import UC_ARM_REG_R3
 run(sb,0x0804bb00,{UC_ARM_REG_R0:BANK+SIZE*slot,UC_ARM_REG_R1:slot,UC_ARM_REG_R2:letter,UC_ARM_REG_R3:1})

def bus(sb,slot,number,value):
 sb.w(EVENT,bytes([0xB0,slot,3,0xFF,number,value]));run(sb,0x08019D40,{UC_ARM_REG_R0:EVENT});run(sb,0x08019CF0)

def values(sb,slot,lane=0):return sb.r(CC+(slot-1)*528+lane*132,132)

def record_and_play():
 for slot in (1,2,3):
  sb=bench(BUNDLE)
  for t in (1,2,3):seed(sb,t)
  advance(sb,slot,1);bus(sb,slot,74,0);bus(sb,slot,74,127)
  assert values(sb,slot)[0]==75
  assert values(sb,slot)[5]==128,values(sb,slot).hex()
  bus(sb,slot,1,0);assert values(sb,slot,1)[5]==1
  assert all(not any(values(sb,t)) for t in (1,2,3) if t!=slot)
  for cc in (2,3,4):bus(sb,slot,cc,55)
  assert sb.r(0x1000bd90+slot-1,1)==b'\1'
  before=sb.r(CC,1584);sb.w(0x2000CAD0,b'\0');bus(sb,slot,74,55);assert sb.r(CC,1584)==before
  # Observe the stock output queue from a real native step boundary, not just helper calls.
  got=[]
  def capture(uc,addr,size,user):
   msg=sb.r(uc.reg_read(UC_ARM_REG_R1),6)
   if msg[0]==0xb0:got.append(msg)
   uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  sb.uc.hook_add(UC_HOOK_CODE,capture,begin=0x08019840,end=0x08019840)
  advance(sb,slot,2);advance(sb,slot,3);advance(sb,slot,0);advance(sb,slot,1)
  assert any(m[4:]==bytes([74,127]) for m in got),[m.hex() for m in got]
 print('PASS real MIDI bus records zero/latest values on each track and native steps emit CC')

def cv_and_isolation():
 sb=bench(BUNDLE);payload=bytearray(528);payload[:4]=bytes([75,1,0,127]);seed(sb,1,payload)
 sb.w(0x20001bac,struct.pack('<4H',0,4095,2048,123))
 advance(sb,1,1);assert values(sb,1)[5]==1
 sb.w(0x20001bac,struct.pack('<H',4095));advance(sb,1,2);assert values(sb,1)[6]==128
 sb.w(0x2000CAD0,b'\0');sb.w(0x20001bac,b'\0\0');advance(sb,1,3);assert values(sb,1)[7]==0
 assert sb.r(OWN,4)==struct.pack('<I',LETTER+1)
 # Foreign ownership blocks both capture and playback.
 sb.w(OWN,struct.pack('<I',1));before=values(sb,1);sb.w(0x2000CAD0,b'\2');bus(sb,1,74,33);assert values(sb,1)==before
 print('PASS CV input samples native normalized ADC endpoints, respects arm and ownership')

def persistence():
 sb=bench(BUNDLE);payload=bytearray(528);payload[:4]=bytes([75,2,0,127]);payload[5]=1;payload[6]=128;seed(sb,1,payload)
 block=TRACKS[1]+0x34+0x194*LETTER
 sb.w(block+4,b'\1\0');sb.w(block+8+3,bytes([60,90,0]));sb.w(block+0x188,struct.pack('<HH',4,4))
 neutralize(sb,0x080232A0,0x080232B0,0x0801EDD4)
 files={};install_fatfs(sb,files)
 run(sb,0x0801C450,{UC_ARM_REG_R1:block,UC_ARM_REG_R2:LETTER})
 data=files[b'patternE.txt'];native=data[:data.index(b'\0')];cc=data[-2188-540:-2188]
 assert cc[:8]==b'\0GCC1\0\0\0',cc[:16].hex()
 assert cc[8:536]==payload
 assert cc[536:]==struct.pack('<I',zlib.crc32(payload))
 assert data[-2188:-2180]==b'\0GCP1\0\0\0'
 for mode in ('valid','bad_crc','missing','legacy'):
  reloaded=Sandbox(BUNDLE);reloaded.w(TRACKS[1]+0x2e,bytes([LETTER]));neutralize(reloaded,0x080232A0,0x080232B0,0x080190A6)
  candidate=data
  if mode=='bad_crc':candidate=data[:-2189]+bytes([data[-2189]^1])+data[-2188:]
  if mode=='legacy':candidate=native+data[-2188:]
  install_fatfs(reloaded,{} if mode=='missing' else {b'patternE.txt':candidate})
  reloaded.w(CC,b'\xa5'*528)
  run(reloaded,0x0801CCC4,{UC_ARM_REG_R0:block,UC_ARM_REG_R1:LETTER,UC_ARM_REG_R2:0})
  assert reloaded.r(CC,528)==(bytes(payload) if mode=='valid' else bytes(528)),(mode,reloaded.r(CC,20).hex())
 print('PASS native writer and fresh loader round-trip CC plus chords; corrupt, absent and legacy files clear automation')
 # Export the firmware-generated fixture for independent JavaScript codec verification.
 (ROOT/'testdata/cc-pattern.fixture.txt').write_bytes(data)

def mutations():
 from unicorn.arm_const import UC_ARM_REG_R4,UC_ARM_REG_R10
 sb=bench(BUNDLE);seed(sb,1);advance(sb,1,1)
 sb.w(0x08019d34,Sandbox().r(0x08019d34,4));bus(sb,1,74,99);assert not any(values(sb,1))
 sb=bench(BUNDLE);payload=bytearray(528);payload[:4]=bytes([75,1,0,127]);seed(sb,1,payload)
 sb.w(0x08021a82,Sandbox().r(0x08021a82,4));advance(sb,1,1);assert values(sb,1)[5]==0
 print('PASS restoring each input/player call independently removes CC capture')




def lifecycle_and_cc_only():
 from unicorn.arm_const import UC_ARM_REG_R3,UC_ARM_REG_R4
 # A native file with no notes must still retain recorded automation.
 sb=bench(BUNDLE);payload=bytearray(528);payload[:4]=bytes([75,1,0,127]);seed(sb,1,payload)
 advance(sb,1,1);block=TRACKS[1]+0x34+0x194*LETTER
 neutralize(sb,0x080232A0,0x080232B0,0x0801EDD4)
 files={};install_fatfs(sb,files);run(sb,0x0801C450,{UC_ARM_REG_R1:block,UC_ARM_REG_R2:LETTER})
 assert b'patternE.txt' in files and files[b'patternE.txt'][-2728:-2720]==b'\0GCC1\0\0\0'
 # Re-enter helper hooks through their original native clear/rotation entry points.
 sb=bench(BUNDLE);payload=bytearray(528);payload[:4]=bytes([75,0,0,0]);payload[4:8]=bytes([1,2,3,4]);seed(sb,1,payload)
 run(sb,SYMS['cc_rotate'],{UC_ARM_REG_R0:block,UC_ARM_REG_R1:1});assert values(sb,1)[4:8]==bytes([4,1,2,3])
 run(sb,SYMS['cc_clear_step'],{UC_ARM_REG_R0:block,UC_ARM_REG_R1:1});assert values(sb,1)[4:8]==bytes([4,0,2,3])
 run(sb,SYMS['cc_clear'],{UC_ARM_REG_R0:block});assert not any(values(sb,1))
 # Chain publication installs the CC staging records and new owner as one bank handoff.
 seed(sb,1,payload,letter=0);sb.w(SNAP+8,bytes(reversed(payload)));sb.w(VALID,struct.pack('<I',1))
 # Use a structurally valid incoming bank; the copy helper also validates native notes.
 incoming=bytearray(528);incoming[:4]=bytes([2,0,0,0]);incoming[5]=81;sb.w(SNAP+8,incoming)
 run(sb,0x0804c500,{UC_ARM_REG_R0:BANK+SIZE,UC_ARM_REG_R1:1,UC_ARM_REG_R2:4,UC_ARM_REG_R3:0})
 assert not any(values(sb,1)), 'failed incoming chord load retained old CC'
 assert sb.r(OWN,4)==struct.pack('<I',5)
 print('PASS CC-only patterns save, lane helpers mutate bounded values, and missing chain data clears CC')




def native_lifecycle():
 from unicorn.arm_const import UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R10,UC_ARM_REG_R11
 payload=bytearray(528);payload[:4]=bytes([75,0,0,0]);payload[4:8]=bytes([1,2,3,4])
 for mutant in (False,True):
  sb=bench(BUNDLE);seed(sb,1,payload);block=TRACKS[1]+0x34+0x194*LETTER
  if mutant:sb.w(0x0801a4e6,Sandbox().r(0x0801a4e6,4))
  run(sb,0x0801a4d0,{UC_ARM_REG_R0:block})
  assert bool(any(values(sb,1)))==mutant
 for inline in (False,True):
  sb=bench(BUNDLE);seed(sb,1,payload);block=TRACKS[1]+0x34+0x194*LETTER
  regs={UC_ARM_REG_R4:block} if inline else {UC_ARM_REG_R4:block-0x34,UC_ARM_REG_R7:TRACKS[1],UC_ARM_REG_R8:block,UC_ARM_REG_R10:LETTER,UC_ARM_REG_R11:0x194}
  run(sb,0x0802f2de if inline else 0x0802bec2,regs,stop=0x0802f306 if inline else 0x0802befc)
  assert not any(values(sb,1)), 'hard delete left automation behind'
 for direction in (0,1):
  sb=bench(BUNDLE);seed(sb,1,payload);block=TRACKS[1]+0x34+0x194*LETTER
  neutralize(sb,0x080232A0,0x080232B0)
  def selected(uc,addr,size,user):uc.reg_write(UC_ARM_REG_R0,TRACKS[1]);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  sb.uc.hook_add(UC_HOOK_CODE,selected,begin=0x08023320,end=0x08023320)
  run(sb,0x0802a0c8,{UC_ARM_REG_R0:direction})
  assert values(sb,1)[4:8]==(bytes([4,1,2,3]) if direction else bytes([2,3,4,1]))
 print('PASS native clear, both hard-delete paths and both rotations keep populated CC banks synchronized')


def save_as_and_inactive():
 from unicorn.arm_const import UC_ARM_REG_R3
 data=(ROOT/'testdata/cc-pattern.fixture.txt').read_bytes();payload=data[-2720:-2192]
 sb=bench(BUNDLE);seed(sb,1,payload);block=TRACKS[1]+0x34+0x194*LETTER
 sb.w(block+4,b'\1\0');sb.w(block+8,bytes([60,90,0]));neutralize(sb,0x080232A0,0x080232B0,0x0801EDD4)
 files={};install_fatfs(sb,files);run(sb,0x0801c450,{UC_ARM_REG_R1:block,UC_ARM_REG_R2:0})
 assert files[b'patternA.txt'][-2720:-2192]==payload
 assert sb.r(OWN,4)==struct.pack('<I',LETTER+1)
 sb=bench(BUNDLE);other=bytearray(528);other[:4]=bytes([12,0,0,0]);other[4]=77;seed(sb,1,other,letter=0)
 sb.w(TRACKS[1]+0x2e,b'\0');sb.w(OWNER+4,struct.pack('<I',1))
 sb.w(block+4,b'\1\0');sb.w(block+8,bytes([60,90,0]));neutralize(sb,0x080232A0,0x080232B0,0x0801EDD4)
 files={b'patternE.txt':data};install_fatfs(sb,files);run(sb,0x0801c450,{UC_ARM_REG_R1:block,UC_ARM_REG_R2:LETTER})
 assert files[b'patternE.txt'][-2720:-2192]==payload
 assert sb.r(CC,528)==other
 print('PASS native Save As copies automation and inactive overwrite preserves its own embedded records')


if __name__=="__main__":record_and_play();cv_and_isolation();persistence();mutations();lifecycle_and_cc_only();native_lifecycle();save_as_and_inactive()
