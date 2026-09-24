#!/usr/bin/env python3
"""Compile the real firmware functions against deterministic USB/RTOS stubs."""
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]

def extract(path, start, end):
    source = (ROOT / path).read_text()
    return source[source.index(start):source.index(end, source.index(start))]

def run(source):
    with tempfile.TemporaryDirectory() as temp:
        source_file = pathlib.Path(temp) / 'test.c'
        binary = pathlib.Path(temp) / 'test'
        source_file.write_text(source)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(source_file), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)

run(r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#define CANFD_FEATURE_ENABLED 1
#define GS_CAN_FLAG_FD 2
#define GS_HOST_FRAME_SIZE 80
#define GS_HOST_CLASSIC_FRAME_SIZE 24
#define GSUSB_ENDPOINT_IN 0x81
#define USBD_OK 0
#define USBD_BUSY 1
#define USBD_FAIL 2
struct gs_host_frame { uint32_t echo_id,can_id; uint8_t dlc,channel,flags,reserved; uint8_t data[64]; uint32_t timestamp; };
typedef struct { volatile unsigned TxState; unsigned timestamps_enabled,pad_pkts_to_max_pkt_size; } USBD_GS_CAN_HandleTypeDef;
typedef struct { void *pClassData; } USBD_HandleTypeDef;
static uint8_t wire[80]; static uint8_t *inflight; static size_t total; static int calls,fail;
int USBD_LL_Transmit(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *buf,uint16_t len) {
 (void)p;(void)ep; calls++; if(fail)return USBD_FAIL;
 inflight=buf; total=len; memcpy(wire,buf,len<64?len:64); return USBD_OK;
}
''' + extract('Core/Src/usbd_gs_can.c', 'uint8_t USBD_GS_CAN_SendFrame(', '\nbool USBD_GS_CAN_CustomDeviceRequest') + r'''
int main(void) {
 for(int fd=0;fd<2;fd++)for(int ts=0;ts<2;ts++)for(int pad=0;pad<2;pad++) {
  USBD_GS_CAN_HandleTypeDef state={0}; state.timestamps_enabled=ts;state.pad_pkts_to_max_pkt_size=pad;
  USBD_HandleTypeDef dev={&state};struct gs_host_frame frame={0};frame.flags=fd?GS_CAN_FLAG_FD:0;
  memset(frame.data,0x11,64);frame.timestamp=0x12345678;
  uint8_t expected[80]={0};size_t len=(fd?80:24)-(ts?0:4);memcpy(expected,&frame,len);
  calls=0;assert(USBD_GS_CAN_SendFrame(&dev,&frame)==USBD_OK);assert(total==(pad?80:len));
  memset(frame.data,0x22,64);frame.timestamp=0xabcdef00;
  assert(USBD_GS_CAN_SendFrame(&dev,&frame)==USBD_BUSY);assert(calls==1);
  if(total>64)memcpy(wire+64,inflight+64,total-64);
  assert(memcmp(wire,expected,total)==0);
  state.TxState=0;assert(USBD_GS_CAN_SendFrame(&dev,&frame)==USBD_OK);assert(calls==2);
  state.TxState=0;fail=1;assert(USBD_GS_CAN_SendFrame(&dev,&frame)==USBD_FAIL);assert(state.TxState==0);fail=0;
 }
 puts("USB buffer lifetime, busy retry, transfer length/padding, and start failure: PASS (8 profiles)");
}
''')

run(r'''
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#define UNUSED(x) (void)(x)
#define portMAX_DELAY 0xffffffffu
#define pdPASS 1
#define USBD_OK 0
#define USBD_BUSY 1
struct gs_host_frame { uint8_t channel; uint32_t sequence; };
struct gs_host_frame_object { struct gs_host_frame frame; };
struct { int queue_to_hostHandle; } hGS_CAN;
int hUSB;
static jmp_buf done;
static int dequeues,sends,yields,callbacks;
int xQueueReceive(int q,struct gs_host_frame *f,unsigned ticks) {
 (void)q;(void)ticks;dequeues++;assert(dequeues==1);f->channel=0;f->sequence=42;return pdPASS;
}
int USBD_GS_CAN_SendFrame(int *dev,struct gs_host_frame *f) {
 (void)dev;assert(f->sequence==42);return ++sends<4?USBD_BUSY:USBD_OK;
}
void taskYIELD(void) { yields++; }
void can_on_rx_cb(uint8_t channel,struct gs_host_frame *f) {
 assert(channel==0 && f->sequence==42);callbacks++;longjmp(done,1);
}
''' + extract('Core/Src/main.c','void task_queue_to_host(void *argument)\n{','\n/*\n * Functions for handling the transition to bootloader') + r'''
int main(void) {
 if(!setjmp(done))task_queue_to_host(NULL);
 assert(dequeues==1 && sends==4 && yields==3 && callbacks==1);
 puts("USB busy retains the dequeued frame without requeue or another dequeue: PASS");
}
''')
