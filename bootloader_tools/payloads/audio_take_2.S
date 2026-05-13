// This file should not exist, but because the ULP lacks some....
// necessary features, the sample data to write to the DAC for the
// audio playback will be written into the .text section as pre-encoded
// instructions. This binary is also huge and should be slimmed down. 

.data
.global active_array
    active_array: .int 0

.text
.global entry
entry:
    move r3, active_array

loop:
.global sample_array0
    sample_array0: .space 2920 // 2920 entries

    // Signal the main CPUs to refill the bottom half of the instruction array
    // it's 2920 bytes but we can only fit 365 samples in it...
    move r1, 0 // +6 cycles, array0 half needs refill
    st r1, r3, 0  // +8 Cycles
    wait 5 // +11 Cycles
    //jump loop
    // Total: 25 cycles latency

.global sample_array1
    sample_array1: .space 2920

    // Signal the main CPUs to refill the top half of the instruction array
    // it's 2920 bytes but we can only fit 365 samples in it...
    move r1, 1 // +6 Cycles; array1 no longer active
    st r1, r3, 0  // + 8 Cycles
    wait 1 // +7 cycles
    jump loop  // +4 Cycles
    // Total: 25 cycles latency