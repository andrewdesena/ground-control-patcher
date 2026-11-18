#!/usr/bin/env python3
"""Compile and relocate a freestanding Thumb CC candidate, preserving the baseline bundle."""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from elftools.elf.elffile import ELFFile
from asm import assemble
from thumbfix import decode_t4,encode_t4
ROOT=Path(__file__).resolve().parent.parent
CATALOG=json.loads((ROOT/'firmware/releases.json').read_text())
CANDIDATE=CATALOG['candidate']
BASE=ROOT/'mods/v1-poly-v120-boot1.json'
CODE=0x0804d000
WRAP=0x08052000

def compile_code():
 with tempfile.TemporaryDirectory() as td:
  obj=Path(td)/'cc.o'
  subprocess.run(['clang','--target=thumbv7em-none-eabi','-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft','-Oz','-ffreestanding','-fno-builtin','-fno-jump-tables','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector','-c',str(ROOT/'firmware/cc_automation.c'),'-o',str(obj)],check=True)
  with obj.open('rb') as f:
   elf=ELFFile(f);sec=elf.get_section_by_name('.text');data=bytearray(sec.data());symtab=elf.get_section_by_name('.symtab');symbols={s.name:CODE+(s['st_value']&~1) for s in symtab.iter_symbols() if s['st_shndx']==elf.get_section_index('.text')}
   for section in elf.iter_sections():
    if section.name!='.rel.text':continue
    for r in section.iter_relocations():
     off=r['r_offset'];sym=symtab.get_symbol(r['r_info_sym']);typ=r['r_info_type']
     if sym.name not in symbols:raise RuntimeError('Unresolved '+sym.name)
     if typ not in (10,30):raise RuntimeError('Unsupported relocation '+str(typ))
     kind,addend=decode_t4(data[off:off+4]);data[off:off+4]=encode_t4(kind,symbols[sym.name]-CODE+addend-off)
  assert CODE+len(data)<WRAP
  return data,symbols

def build():
 code,sym=compile_code();bundle=json.loads(BASE.read_text());patches=bundle['patches'];extra=[]
 def add(addr,lines,note):extra.append({'addr':hex(addr),'bytes':assemble(lines,addr).hex(),'note':note})
 def wrapper(index,lines,note):addr=WRAP+index*0x100;add(addr,lines,note);return hex(addr)
 def call(name):return 'bl '+hex(sym[name])
 # Preserve the original entry instructions and ABI, then resume stock dispatch.
 a=wrapper(0,['push {r0-r3, r12, lr}',call('cc_input'),'pop {r0-r3, r12, lr}','b.w 0x08019c84'],'CC transformed MIDI bus input')
 add(0x08019d34,['bl '+a],'Observe incoming CC without changing stock event delivery')
 a=wrapper(1,['push {r1-r3, lr}','mov r0, r4','mov r1, r10',call('cc_tick'),'pop {r1-r3, lr}','b.w 0x080232e4'],'Step-boundary CV capture and CC playback')
 add(0x08021a82,['bl '+a],'One automation pass per native melodic step')
 a=wrapper(2,['push {r0-r3, r12, lr}','mov r1, r2',call('cc_read'),'pop {r0-r3, r12, lr}','push {r4-r8, lr}','sub sp, #8','b.w 0x0804b90a'],'Read optional automation before the original bounded chord reader')
 add(0x0804b904,['b.w '+a],'CC staging read in the SD task')
 a=wrapper(3,['push {r0-r3, r12, lr}','mov r0, r1','mov r1, r2','mov r2, r3',call('cc_publish'),'pop {r0-r3, r12, lr}','push {r4-r7, lr}','ldr r4, =0x1000d758','b.w 0x0804bb04','.ltorg'],'Publish CC with the native active bank')
 add(0x0804bb00,['b.w '+a],'Active-pattern CC publication')
 a=wrapper(4,['push {r0-r3, r12, lr}','mov r0, r1','mov r1, r2','mov r2, r3',call('cc_publish'),'pop {r0-r3, r12, lr}','push {r4-r11, lr}','b.w 0x0804c504'],'Publish CC with deferred chain chords')
 add(0x0804c500,['b.w '+a],'Chain CC publication')
 a=wrapper(5,['push {r0-r3, r12, lr}','mov r0, r4',call('cc_allow_stock'),'cmp r0, #0','beq skip','pop {r0-r3, r12, lr}','b.w 0x08019ace','skip:','pop {r0-r3, r12, lr}','movs r0, #0','bx lr'],'An explicit CC1 lane replaces native modulation-wheel playback')
 add(0x08021c2a,['bl '+a],'Prevent duplicate native CC1 when an automation lane owns it')
 # Reassemble the two existing routines so CC snapshots share the writer lock.
 source=json.loads((ROOT/'mods/poly-single-file.source.json').read_text())
 writer=source['cave']['asm'];i=writer.index('ldr r5, =0x1000e4f8');writer[i:i]=['mov r0, r8',call('cc_write')];add(0x08047e00,writer,'Append CC block before the unchanged GCP1 tail')
 snapshot=next(p['asm'] for p in source['patches'] if p['addr']=='0x0804bd00');i=snapshot.index('unlock:');snapshot[i:i]=['mov r0, r4',call('cc_snapshot')];add(0x0804bd00,snapshot,'Snapshot CC while native writer lock is held')
 # Integrate whole clear, fill clear, rotations and hard delete with existing hooks.
 mutations=json.loads((ROOT/'mods/poly-lifecycle-mutations.source.json').read_text())
 for p,name,args in [(mutations['patches'][0],'cc_clear',[]),(mutations['patches'][1],'cc_clear_step',['mov r0, r4','mov r1, r7']),(mutations['patches'][2],'cc_rotate',['mov r0, r4','mov r1, r8'])]:
  lines=p['asm'];idx=lines.index('bl 0x0804b000');lines[idx:idx]=args+[call(name)]+(['mov r0, r4'] if args else [])
  if name=='cc_clear':lines[lines.index(call(name))+1:lines.index(call(name))+1]=['ldr r0, [sp]']
  add(int(p['addr'],16),lines,'Keep automation synchronized with '+name)
 hard=json.loads((ROOT/'mods/poly-harddelete.source.json').read_text())['cave']['asm'];i=hard.index('bl 0x0804b000');hard[i:i]=['push {r0, lr}',call('cc_clear'),'pop {r0, lr}'];add(0x0804b700,hard,'Hard delete clears automation')
 # Allow the optional CC block in addition to the original native-text bound.
 # Keep the stock tokenizer's 10,200-byte native text buffer unchanged.
 reader=next(p['asm'] for p in source['patches'] if p['addr']=='0x0804b900');reader=reader.copy();reader[reader.index('movw r0, #0x27d8')]='movw r0, #10740'
 # Reader entry has the new trampoline; retain its first four bytes then replace prologue.
 data=bytearray(assemble(reader,0x0804b900));data[4:8]=assemble(['b.w '+hex(WRAP+2*0x100)],0x0804b904);extra.append({'addr':'0x804b900','bytes':data.hex(),'note':'Bounded GCP1 reader accepting the optional 540-byte extension'})
 # Drop fragment hooks that are now contained by a reassembled full routine.
 extra=[p for p in extra if int(p['addr'],16)!=0x0804b904]
 extra.append({'addr':hex(CODE),'bytes':bytes(code).hex(),'note':'Freestanding bounded CC runtime and codec'})
 by_addr={int(p['addr'],16):p for p in patches}
 for p in extra:
  address=int(p['addr'],16);old=by_addr.get(address)
  if old and len(p['bytes'])<len(old['bytes']):p=dict(p,bytes=p['bytes']+old['bytes'][len(p['bytes']):])
  by_addr[address]=p
 final=sorted(by_addr.values(),key=lambda p:int(p['addr'],16))
 # Overlap is forbidden, including expansion into a neighboring routine.
 for a,b in zip(final,final[1:]):
  assert int(a['addr'],16)+len(bytes.fromhex(a['bytes']))<=int(b['addr'],16),(a['addr'],b['addr'])
 bundle.update(name='Polyphony + CC automation',version=CANDIDATE['version'],legacyBuild=CANDIDATE['legacyBuild'],status='experimental',description='Candidate: step-quantized MIDI CC and external CV recording with single-file automation.',patches=final)
 bundle['requires']['blank']=[['0x08046810','0x0804a000'],[hex(CODE),hex(WRAP+0x600)]]
 dest=ROOT/CANDIDATE['bundle'];dest.write_text(json.dumps(bundle,indent=2)+'\n')
 (ROOT/'firmware/cc-symbols.json').write_text(json.dumps({k:hex(v) for k,v in sym.items() if k.startswith('cc_')},indent=2)+'\n')
 subprocess.run([sys.executable,str(ROOT/'tools/apply.py'),str(dest),str(ROOT/CANDIDATE['filename'])],check=True)
 print('Candidate SHA-256',hashlib.sha256((ROOT/CANDIDATE['filename']).read_bytes()).hexdigest())
if __name__=='__main__':build()
