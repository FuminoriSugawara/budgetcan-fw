import socket, struct, time, json, sys, select
from pathlib import Path
import os
Path(os.environ.get('CAN_TEST_OUTPUT', '/tmp/budgetcan-validation')).mkdir(parents=True,exist_ok=True)
mode, peer = sys.argv[1:3]
fd = mode != 'classic'
brs = mode == 'fd-brs'
sizes = list(range(9)) + ([12,16,20,24,32,48,64] if fd else [])
socks = []
results = []
for name in ['can0',peer]:
 s = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
 s.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_FD_FRAMES, 1)
 s.setsockopt(socket.SOL_CAN_RAW, socket.CAN_RAW_RECV_OWN_MSGS, 0)
 s.setsockopt(socket.SOL_CAN_RAW, 2, struct.pack('=I',0x1fffffff))
 s.bind((name,)); s.settimeout(1); socks.append(s)
try:
 for a,b in [(0,1),(1,0)]:
  count=0
  for i in range(1000):
   n=sizes[i%len(sizes)]
   ident=(0x123+a) if i%2==0 else (0x80000000|0x1234567+a)
   data=bytes((i*37+j*13+a)&255 for j in range(n))
   frame=struct.pack('=IBBBB',ident,n,int(brs),0,0)+data.ljust(64 if fd else 8,b'\0')
   socks[a].send(frame)
   got=socks[b].recv(72)
   rid,rlen,flags,_,_=struct.unpack('=IBBBB',got[:8])
   if rid&0x20000000: raise RuntimeError('CAN error frame: '+got.hex())
   if (rid,rlen,got[8:8+rlen],len(got))!=(ident,n,data,len(frame)) or (fd and flags&1!=int(brs)):
    raise RuntimeError('mismatch sent='+frame.hex()+' received='+got.hex())
   count+=1
   time.sleep(.002)
  ready,_,_=select.select(socks,[],[],.1)
  if ready: raise RuntimeError('unexpected additional/error frame: '+ready[0].recv(72).hex())
  results.append({'from':['can0',peer][a],'to':['can0',peer][b],'frames':count,'payload_lengths':sizes,'standard_and_extended_id':True,'exact_match':True})
  print(json.dumps(results[-1]),flush=True)
 report={'mode':mode,'passed':True,'results':results}
except Exception as e:
 report={'mode':mode,'passed':False,'results':results,'error':repr(e)}
finally:
 for s in socks:s.close()
(Path(os.environ.get('CAN_TEST_OUTPUT', '/tmp/budgetcan-validation')) / (mode+'.json')).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
sys.exit(0 if report['passed'] else 1)
