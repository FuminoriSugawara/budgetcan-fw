# USB transmit buffer lifetime for CAN FD

When receiving consecutive 64-byte CAN FD frames, the last 12 bytes sent to the host can contain data from another frame.
Starting a USB transfer copies only the first 64 bytes into USB peripheral memory; subsequent interrupts read the remaining bytes.
The caller could overwrite the same frame variable with the next queue entry before those reads completed.
With a 12-byte USB header, the first packet contains 52 bytes of CAN payload, leaving the final 12 bytes exposed to this overwrite.

The fix copies each frame into a dedicated static buffer and retains its contents until the USB transfer completes.
While a transfer is active, the function returns BUSY before copying any data, preserving the buffer whether packet padding is enabled or disabled.
If the lower layer fails to start the transfer, the function clears the transmit state so the caller can retry.
Only the single host transmit task may call this function.

The host transmit task retains the dequeued frame and retries instead of returning it to the queue when USB is busy.
This prevents the task from losing that frame if an interrupt fills the queue before it can be requeued.
Yielding between retries allows other tasks to run, as the previous zero-tick delay did.
This change does not guarantee lossless operation when incoming traffic exceeds the queue's processing capacity.

The fix was initially developed from commit `e8fb8efebdac22019dc7e73dfec773c6fd2ec5a8`, which corresponds to the distributed firmware binary.
Because the original repository was unavailable, the source was forked from `sivan-ui/budgetcan-fw`, which retains that commit.

## Build and regression tests

The build requires `arm-none-eabi-gcc` and a host C compiler available as `cc`.

```sh
git submodule update --init Drivers/stm32g4xx_hal_driver Drivers/cmsis_device_g4
python3 tests/test_usb_tx.py
make -C Portable/board_canablev2 -j4
```

The regression tests compile the actual transmit functions with stubs that simulate the caller overwriting its memory between USB packets.
They cover eight combinations of Classic CAN or CAN FD, timestamps enabled or disabled, and padding enabled or disabled.
They also verify buffer retention while busy, recovery after a transfer fails to start, and retrying the same dequeued frame without requeueing it.
Host-side simulations do not establish correct hardware operation; hardware CAN communication results are recorded separately.
