/* Experimental CC extension for stock v3.26 plus v1.20-boot1.
 * The unused drum chord bank is partitioned into three CC banks and one SD snapshot.
 * No heap, peripheral writes, SD access from MIDI input or step playback callbacks.
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
#define P8(a) ((volatile u8 *)(a))
#define P16(a) ((volatile u16 *)(a))
#define P32(a) ((volatile u32 *)(a))
#define BANK_SIZE 528u
#define BLOCK_SIZE 540u
#define SNAP P8(0x1000bb60u)
#define OWN P32(0x1000bd80u)
#define VALID (*P32(0x1000bd8cu))
#define OVERFLOW P8(0x1000bd90u)
#define TRACKS P32(0x08038370u)
#define NOTE_OWN P32(0x1000d740u)
#define CV_RAW P16(0x20001bacu)
#define FN(addr, type) ((type)((addr) | 1u))
#define INLINE static __attribute__((always_inline)) inline
INLINE u32 irq_lock(void) { u32 m; __asm__ volatile("mrs %0, primask\n cpsid i":"=r"(m)::"memory"); return m; }
INLINE void irq_restore(u32 m) { __asm__ volatile("msr primask, %0"::"r"(m):"memory"); }
INLINE volatile u8 *bank(u32 slot) { return P8(0x1000b530u + (slot-1u)*BANK_SIZE); }
INLINE u32 recorder(u32 slot) { return 0x2000c848u - (slot-1u)*0xf4u; }
INLINE u32 crc(volatile u8 *bytes,u32 size) { u32 c=~0u;for(u32 i=0;i<size;i++){c^=bytes[i];for(u32 b=0;b<8;b++)c=(c>>1)^((c&1)?0xedb88320u:0);}return ~c; }
INLINE void zero(volatile u8 *p,u32 n){for(u32 i=0;i<n;i++)p[i]=0;}
INLINE void copy(volatile u8 *to,volatile u8 *from,u32 n){for(u32 i=0;i<n;i++)to[i]=from[i];}
INLINE u32 get32(volatile u8 *p){return p[0]|((u32)p[1]<<8)|((u32)p[2]<<16)|((u32)p[3]<<24);}
INLINE void put32(volatile u8 *p,u32 value){for(u32 i=0;i<4;i++)p[i]=(u8)(value>>(8*i));}
INLINE u32 identify(u32 rec){u32 track=*P32(rec+8),slot=*P8(track+0x1f);return slot>=1&&slot<=3&&TRACKS[slot]==track?slot:0;}
INLINE int active(u32 slot){u32 track=TRACKS[slot],letter=*P8(track+0x2e);return letter<24&&OWN[slot-1]==letter+1&&NOTE_OWN[slot]==letter+1;}
INLINE int armed(u32 rec){return *P8(0x200030deu)!=0&&*P8(0x2000cad0u)==2;}
INLINE int valid_step(u32 slot,u32 step){u32 track=TRACKS[slot],block=track+0x34+0x194u*(*P8(track+0x2e)),n=*P16(block+0x188);return n>=1&&n<=128&&step<n;}
INLINE void dirty(u32 slot,u32 step){u32 track=TRACKS[slot],block=track+0x34+0x194u*(*P8(track+0x2e));*P16(block+4)=1;if(*P16(block+0x18a)<step+1)*P16(block+0x18a)=(u16)(step+1);}
INLINE void record_value(u32 slot,u32 step,u32 number,u32 value){
 volatile u8 *b=bank(slot),*free=0;
 for(u32 l=0;l<4;l++){volatile u8 *lane=b+l*132;if(lane[0]==number+1){if(lane[1])return;lane[4+step]=(u8)(value+1);dirty(slot,step);return;}if(!lane[0]&&!free)free=lane;}
 if(!free){OVERFLOW[slot-1]=1;return;}zero(free,132);free[0]=(u8)(number+1);free[4+step]=(u8)(value+1);dirty(slot,step);
}
/* Called from the stock transformed input bus. */
void cc_input(volatile u8 *event){
 if(event[0]!=0xb0||event[4]>127||event[5]>127)return;
 u32 mask=irq_lock();
 for(u32 slot=1;slot<=3;slot++){
  u32 rec=recorder(slot),step=*P8(rec+0x3c);if(!active(slot)||!armed(rec)||step>127||!valid_step(slot,step))continue;
  if(event[1]!=*P8(0x2001bb38u+0xb9+slot)&&!*P8(0x2001bb38u+0xcb+slot))continue;
  record_value(slot,step,event[4],event[5]);
 }
 irq_restore(mask);
}
/* Called once after the native player resolves its step, including silent steps. */
void cc_tick(u32 rec,u32 time){
 u32 slot=identify(rec);if(!slot||!*P8(0x200030deu))return;
 u32 mask=irq_lock(),step=*P8(rec+0x3c);if(!active(slot)||step>127||!valid_step(slot,step)){irq_restore(mask);return;}
 u8 numbers[4],values[4];u32 count=0;volatile u8 *b=bank(slot);
 for(u32 l=0;l<4;l++){
  volatile u8 *lane=b+l*132;u32 number=lane[0];if(!number||number>128)continue;
  if(armed(rec)&&lane[1]>=1&&lane[1]<=4){u32 raw=CV_RAW[lane[1]-1];if(raw>4095)raw=4095;u32 lo=lane[2],hi=lane[3];if(lo>127)lo=0;if(hi>127)hi=127;u32 v=lo<=hi?lo+((hi-lo)*raw+2047)/4095:lo-((lo-hi)*raw+2047)/4095;lane[4+step]=(u8)(v+1);dirty(slot,step);}
  u32 code=lane[4+step];if(code&&code<=128){numbers[count]=(u8)(number-1);values[count]=(u8)(code-1);count++;}
 }
 irq_restore(mask);
 if(*P8(TRACKS[slot]+0x30))return;
 for(u32 i=0;i<count;i++)FN(0x08019aceu,void(*)(u32,u32,u32,u32,u32,u32))(0,time,*P8(rec+4),numbers[i],values[i],slot);
}
/* Read the optional fixed-size block immediately before the standard GCP1 tail.
 * FIL belongs to the serial SD task; the sample bank is never used for I/O.
 */
void cc_read(char *path,void *fil){
 VALID=0;zero(SNAP,BLOCK_SIZE);
 if(FN(0x0801496cu,int(*)(void*,char*,u32))(fil,path,1))return;
 u32 size=*P32((u32)fil+12),read=0;
 if(size<2188+BLOCK_SIZE+1||size>10200+2188+BLOCK_SIZE)goto close;
 u32 skip=size-2188-BLOCK_SIZE;
 while(skip){u32 n=skip>BLOCK_SIZE?BLOCK_SIZE:skip;read=0;if(FN(0x08014b30u,int(*)(void*,volatile u8*,u32,u32*))(fil,SNAP,n,&read)||read!=n)goto close;skip-=n;}
 read=0;if(FN(0x08014b30u,int(*)(void*,volatile u8*,u32,u32*))(fil,SNAP,BLOCK_SIZE,&read)||read!=BLOCK_SIZE)goto close;
 if(get32(SNAP)!=0x43434700u||get32(SNAP+4)!=0x31u||get32(SNAP+536)!=crc(SNAP+8,BANK_SIZE))goto close;
 for(u32 l=0;l<4;l++){volatile u8 *lane=SNAP+8+l*132;if(lane[0]>128||lane[1]>4||lane[2]>127||lane[3]>127)goto close;for(u32 k=0;k<128;k++)if(lane[4+k]>128)goto close;for(u32 j=0;j<l;j++)if(lane[0]&&lane[0]==SNAP[8+j*132])goto close;}
 VALID=1;
close:
 if(FN(0x08014f18u,int(*)(void*))(fil))VALID=0;
 if(!VALID)zero(SNAP,BLOCK_SIZE);
}
/* Native load and chain publication call this under the same lock as chord data. */
void cc_publish(u32 slot,u32 letter,u32 notes_valid){if(slot<1||slot>3)return;u32 mask=irq_lock();if(notes_valid&&VALID)copy(bank(slot),SNAP+8,BANK_SIZE);else zero(bank(slot),BANK_SIZE);OWN[slot-1]=letter+1;OVERFLOW[slot-1]=0;irq_restore(mask);}
/* Resolver returns the selected pattern's slot and letter without ASCII arithmetic. */
INLINE u32 resolve(u32 block,u32 *letter){for(u32 slot=1;slot<=3;slot++)for(u32 l=0;l<24;l++)if(TRACKS[slot]+0x34+l*0x194==block){*letter=l;return slot;}return 0;}
void cc_snapshot(u32 block){u32 letter=0,slot=resolve(block,&letter);if(!slot){VALID=0;return;}u32 mask=irq_lock();if(OWN[slot-1]==letter+1){copy(SNAP+8,bank(slot),BANK_SIZE);VALID=1;}else if(NOTE_OWN[slot]==letter+1){zero(SNAP+8,BANK_SIZE);VALID=1;}else if(!VALID)zero(SNAP+8,BANK_SIZE);irq_restore(mask);put32(SNAP,0x43434700u);put32(SNAP+4,0x31);put32(SNAP+536,crc(SNAP+8,BANK_SIZE));}
void cc_write(void *fil){if(!VALID)return;u32 present=0,written=0;for(u32 l=0;l<4;l++)present|=SNAP[8+l*132];if(!present)return;FN(0x08014c92u,int(*)(void*,volatile u8*,u32,u32*))(fil,SNAP,BLOCK_SIZE,&written);}
void cc_clear(u32 block){u32 letter=0,slot=resolve(block,&letter),mask=irq_lock();if(slot&&OWN[slot-1]==letter+1)zero(bank(slot),BANK_SIZE);irq_restore(mask);}
void cc_clear_step(u32 block,u32 step){u32 letter=0,slot=resolve(block,&letter),mask=irq_lock();if(slot&&step<128&&OWN[slot-1]==letter+1)for(u32 l=0;l<4;l++)bank(slot)[l*132+4+step]=0;irq_restore(mask);}
void cc_rotate(u32 block,u32 right){u32 letter=0,slot=resolve(block,&letter),n=*P16(block+0x188);if(!slot||n<2||n>128)return;u32 mask=irq_lock();if(OWN[slot-1]!=letter+1){irq_restore(mask);return;}for(u32 l=0;l<4;l++){volatile u8 *values=bank(slot)+l*132+4;u8 saved=values[right?n-1:0];if(right)for(u32 i=n-1;i;i--)values[i]=values[i-1];else for(u32 i=0;i<n-1;i++)values[i]=values[i+1];values[right?0:n-1]=saved;}irq_restore(mask);}
/* An explicit CC1 lane owns modulation-wheel playback, avoiding duplicate native CC1. */
u32 cc_allow_stock(u32 rec){u32 slot=identify(rec);if(slot&&active(slot))for(u32 l=0;l<4;l++)if(bank(slot)[l*132]==2)return 0;return 1;}
