// What needs to be done here:
// Take 2 input buffers, alternate between them, and stuff their contents
// into the DAC.

// RTC IO base address:
#define RTC_RTCIO_GPIO_BASE        0x3ff48400
#define RTCIO_PAD_DAC1_REG         (RTC_RTCIO_GPIO_BASE + 0x84)

.bss
    // Audio samples are double buffered.
    .global sample_array0
        sample_array0: .space 2560  // NOTE: Only 1280B of this buffer are usable.
    .global sample_array1 
        sample_array1: .space 2560

.data
    // Actively playing array (fill the inactive one CPU-side)
    .global active_array
        active_array: .int 0
    // Current sample index for the active array (BYTE INDEX)
    .global sample_index
        sample_index: .int 0
    // Code exec successful
    .global rtc_dumped_sample
        rtc_dumped_sample: .int 0

// I always use r0 as an address register
.text
    .global entry
entry:
    // DAC should be initialized already (since this code should not be running
    // without an active DAC)

    // Phase 1: Get current local sample byte index.

    // Array local index
    move r0, sample_index
    ld r3, r0, 0

    // swap buffers if r3 == 2048 (reached end of buffer)
    sub r2, r3, 2048
    jump buffer_swap, EQ // Buffer switchover required

    // Increment sample index for next run.
    add r3, r3, 1
    st r3, r0, 0

    // Active buffer to use (non swapped)
    move r0, active_array
    ld r2, r0, 0

swap_done:
    // Current registers:
    // r0 (address reg)
    // r1 (sample array address in words)
    // r2 (current array word address)
    // r3 (sample byte index)

    // Phase 2: Read sample value from the correct buffer

    // Adjust offset (0 offset for array0, 2048 offset for array1 (512 word offset))
    lsh r2, r2, 9  // Offset should still be 0 for array0; word address
    move r0, sample_array0
    add r2, r2, r0  // Offset in RTC mem of buffer (still word address)

    // convert byte index to word index + byte offset
    //and r1, r3, 0x1 // Need lsb for +0/+1 offset
    //rsh r3, r3, 2  // Bytes to words

    // Current registers:
    // r0 (address reg)
    // r1 (low/high byte of halfword of sample)
    // r2 (current array word address)
    // r3 (sample word index)

    // Absolute sample address in words
    //add r2, r2, r3
    move r3, r2 // debugging

    // Get the sample (and adjust pointers/r1 is sample)
    //ld r1, r2, 0
    //rsh r1, r1, 2
    //rsh r1, r1, 8 // Get the high half (probably the sample we want???)

    // what sample data
    //move r3, r1

    // Sample load:
    // need word address (then mask out high or low byte depending on the lsb of the absolute address)


    // samples are STILL WRONG?!?!

    // R2 is sample index currently
    // R1 is the actual sample value

    // Current registers:
    // r0 (address of DAC field)
    // r1 (sample value)
    // r2 (current rtc reg val)
    // r3


    // Phase 3: Write the sample to the DAC. The two least significant bytes are
    // not important.
    //move r0, RTCIO_PAD_DAC2_REG
    //ld r2, r0, 0x2
    //and r2, r2, 0xf807 // bit mask: 0b1111100000000111 (eliminate dac value bits)
    //lsh r1, r1, 3 
    //or r2, r2, r1
    //st r2, r0, 0x2

    // Phase 4: Code worked (report if possible)
    move r0, rtc_dumped_sample
    //move r3, 1
    st r3, r0, 0
    halt

    // Okay I give up the memory requirements for this are stupid
    // WHY THE HECK DO I NEED TO WRITE A JUMP TABLE TO FEED AUDIO SAMPLES TO A DAC?!?!?!?
    move r0, RTCIO_PAD_DAC1_REG
    reg_wr 26, 19, 

buffer_swap:
    // FREE REGS:
    // r0 (addrof sample index global)
    // r1
    // r2 (... will be sample array)
    // r3 (sample index)

    // Reset local sample index
    move r3, 0
    st r3, r0, 0

    move r0, active_array
    ld r2, r0, 0

    // Effectively r2 ^ 0b1
    add r2, r2, 1
    and r2, r2, 0x1
    st r2, r0, 0

    jump swap_done
