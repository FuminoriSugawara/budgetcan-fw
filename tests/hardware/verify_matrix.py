import socket,struct,time,select,json,sys
from pathlib import Path
import os
p=Path(os.environ.get('CAN_TEST_OUTPUT', '/tmp/budgetcan-validation')); p.mkdir(parents=True,exist_ok=True)
rate=int(sys.argv[1]); results=[]
for length,window,bidir in [(48,4,False),(64,1,False),(64,4,False),(64,1,True),(64,4,True)]:
 socks=[]
 for name in ['can0','can1']:
  s=socket.socket(socket.PF_CAN,socket.SOCK_RAW,socket.CAN_RAW);s.setsockopt(socket.SOL_CAN_RAW,socket.CAN_RAW_FD_FRAMES,1);s.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1048576);s.bind((name,));s.setblocking(False);socks.append(s)
 sent=[0,0];recv=[0,0];bad=[0,0];pending=[{},{}];examples=[];err=[]
 def frame(a,i):
  data=struct.pack('=Q',i)+bytes((i*37+j*13+a)&255 for j in range(length-8))
  return struct.pack('=IBBBB',0x120+a,length,1,0,0)+data.ljust(64,b'\0')
 start=time.monotonic();end=start+2;last=start
 try:
  while True:
   now=time.monotonic()
   for a in ([0,1] if bidir else [1]):
    while now<end and len(pending[a])<window:
     f=frame(a,sent[a]);socks[a].send(f);pending[a][sent[a]]=f;sent[a]+=1
   ready,_,_=select.select(socks,[],[],.005)
   for s in ready:
    b=socks.index(s);a=1-b
    while True:
     try:g=s.recv(72)
     except BlockingIOError:break
     seq=struct.unpack('=Q',g[8:16])[0];f=pending[a].pop(seq);recv[b]+=1;last=time.monotonic()
     if g[:5]!=f[:5] or g[5]&1!=1 or g[8:8+length]!=f[8:8+length]:
      bad[b]+=1
      if len(examples)<3:examples.append({'receiver':b,'seq':seq,'expected':f.hex(),'received':g.hex(),'offsets':[i for i in range(length) if g[8+i]!=f[8+i]]})
   if time.monotonic()>end and not any(pending):break
   if time.monotonic()-last>1:raise RuntimeError('timeout')
 except Exception as e:err.append(repr(e))
 finally:
  for s in socks:s.close()
 r={'data_bitrate':rate,'length':length,'window':window,'bidirectional':bidir,'elapsed':time.monotonic()-start,'sent':sent,'received':recv,'mismatch':bad,'errors':err,'examples':examples}
 results.append(r);print(json.dumps({k:v for k,v in r.items() if k!='examples'}),flush=True)
 time.sleep(.1)
(p/('matrix-'+str(rate)+'.json')).write_text(json.dumps(results,indent=2))
