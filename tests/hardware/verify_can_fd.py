import socket,struct,time,select,json,errno
from pathlib import Path
import os
p=Path(os.environ.get('CAN_TEST_OUTPUT', '/tmp/budgetcan-validation')); p.mkdir(parents=True,exist_ok=True)
socks=[]
sent=[0,0]; received=[0,0]; retry=[0,0]; overflow=[0,0]
errors=[]; mismatch=[0,0]; unexpected=[0,0]; pending=[{},{}]; examples=[]; window=4; duration=60.0
for name in ['can0','can1']:
 s=socket.socket(socket.PF_CAN,socket.SOCK_RAW,socket.CAN_RAW)
 s.setsockopt(socket.SOL_CAN_RAW,socket.CAN_RAW_FD_FRAMES,1)
 s.setsockopt(socket.SOL_CAN_RAW,2,struct.pack('=I',0x1fffffff))
 s.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1048576)
 s.setsockopt(socket.SOL_SOCKET,40,1)
 s.bind((name,));s.setblocking(False);socks.append(s)
def frame(direction,seq):
 ident=(0x120+direction) if seq%2==0 else (0x80000000|0x123450+direction)
 payload=struct.pack('=Q',seq)+bytes((seq*37+j*13+direction)&255 for j in range(56))
 return struct.pack('=IBBBB',ident,64,1,0,0)+payload
# Establish readiness before the timed run; do not discard failures silently.
handshake=[]
for a,b in [(0,1),(1,0)]:
 expected=struct.pack('=IBBBB',0x700+a,64,1,0,0)+bytes([0x55+a])*64
 socks[a].send(expected)
 ready,_,_=select.select([socks[b]],[],[],1)
 if not ready: raise RuntimeError('readiness handshake timed out')
 got=socks[b].recv(72)
 if len(got)!=72 or got[:5]!=expected[:5] or got[5]&1!=1 or got[8:]!=expected[8:]: raise RuntimeError('readiness handshake mismatch')
 handshake.append({'from':['can0','can1'][a],'to':['can0','can1'][b],'matched':True})
(p/'readiness.json').write_text(json.dumps(handshake,indent=2))
start=time.monotonic();last=[start,start];next_log=start+10
try:
 while True:
  now=time.monotonic()
  if now-start<duration:
   for a in range(2):
    while len(pending[a])<window:
     try:
      f=frame(a,sent[a]); socks[a].send(f); pending[a][sent[a]]=f; sent[a]+=1
     except OSError as e:
      if e.errno in [errno.ENOBUFS,errno.EAGAIN]:retry[a]+=1;break
      raise
  r,_,_=select.select(socks,[],[],.001)
  for s in r:
   b=socks.index(s);a=1-b
   while True:
    try:got,anc,flags,_=s.recvmsg(72,128)
    except BlockingIOError:break
    for level,kind,value in anc:
     if level==socket.SOL_SOCKET and kind==40:overflow[b]=struct.unpack('=I',value)[0]
    if flags&socket.MSG_TRUNC:raise RuntimeError('truncated frame')
    rid=struct.unpack('=I',got[:4])[0]
    if rid&0x20000000:raise RuntimeError('CAN error frame on '+str(b)+': '+got.hex())
    seq=struct.unpack("=Q",got[8:16])[0]
    expected=pending[a].pop(seq,None)
    if expected is None:
     unexpected[b]+=1; continue
    if len(got)!=72 or got[:5]!=expected[:5] or got[5]&1!=1 or got[8:]!=expected[8:]:
     mismatch[b]+=1
     if len(examples)<10:examples.append({'receiver':['can0','can1'][b],'sequence':seq,'expected':expected.hex(),'received':got.hex()})
    received[b]+=1;last[b]=time.monotonic()
  now=time.monotonic()
  for b in range(2):
   if sent[1-b]>received[b] and now-last[b]>2:raise RuntimeError('receive timeout on '+str(b))
  if now>=next_log:
   print(json.dumps({'elapsed_s':round(now-start,3),'sent':sent,'received':received}),flush=True);next_log+=10
  if now-start>=duration and sent==received[::-1]:break
except Exception as e:errors.append(repr(e))
finally:
 elapsed=time.monotonic()-start
 for s in socks:s.close()
r={'passed':not errors and not any(mismatch) and not any(unexpected) and not any(overflow) and elapsed>=duration and sent==received[::-1],'duration_requested_s':duration,'elapsed_s':elapsed,'nominal_bitrate':1000000,'data_bitrate':5000000,'brs':True,'payload_bytes':64,'standard_and_extended_ids':True,'outstanding_window_per_direction':window,'sent_can0_can1':sent,'received_can0_can1':received,'socket_backpressure_retries':retry,'socket_rx_overflow':overflow,'errors':errors,'payload_mismatch_can0_can1':mismatch,'unexpected_sequence_can0_can1':unexpected,'mismatch_examples':examples,'aggregate_frames_per_s':sum(received)/elapsed,'aggregate_payload_mbit_s':sum(received)*64*8/elapsed/1e6}
(p/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
raise SystemExit(0 if r['passed'] else 1)
