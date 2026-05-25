from struct import unpack
import asyncio

_WAVE_FORMAT_PCM = const(0x0001)
_CHK_MAX_READ = const(1024)

class WaveReader:
    """
    RIFF format

    [Master RIFF chunk]
        FileTypeBlocID  (4 bytes) : Identifier « RIFF »  (0x52, 0x49, 0x46, 0x46)
        FileSize        (4 bytes) : Overall file size minus 8 bytes
        FileFormatID    (4 bytes) : Format = « WAVE »  (0x57, 0x41, 0x56, 0x45)

    [Chunk describing the data format]
        FormatBlocID    (4 bytes) : Identifier « fmt␣ »  (0x66, 0x6D, 0x74, 0x20)
        BlocSize        (4 bytes) : Chunk size minus 8 bytes, which is 16 bytes here  (0x10)
        AudioFormat     (2 bytes) : Audio format (1: PCM integer, 3: IEEE 754 float)
        NbrChannels     (2 bytes) : Number of channels
        Frequency       (4 bytes) : Sample rate (in hertz)
        BytePerSec      (4 bytes) : Number of bytes to read per second (Frequency * BytePerBloc).
        BytePerBloc     (2 bytes) : Number of bytes per block (NbrChannels * BitsPerSample / 8).
        BitsPerSample   (2 bytes) : Number of bits per sample

    [Chunk containing the sampled data]
        DataBlocID      (4 bytes) : Identifier « data »  (0x64, 0x61, 0x74, 0x61)
        DataSize        (4 bytes) : SampledData size
        SampledData
    """

    def __init__(self, file_path: str):
        """
        Read a normally formatted WAV file. This file supports any and all PCM encoded
        wav files. Floating point is not currently supported.

        :param file_path: location of the wav on disk.
        """

        self.wav_file = open(file_path, "rb")

        header = RIFFHeader(self.wav_file)
        chunks = self._enumerate_chunks(header)

        format_chunk = self._find_chunk(chunks, b"fmt ")
        self._data_chunk = self._find_chunk(chunks, b"data")

        # Read format block
        format_chunk.seek(0)
        self.format = unpack("<H", format_chunk.read(2))[0]

        if self.format != _WAVE_FORMAT_PCM:
            raise ValueError(f"bad wave format: {self.format}")

        self.num_channels = unpack("<H", format_chunk.read(2))[0]
        self.framerate = unpack("<I", format_chunk.read(4))[0]
        format_chunk.read(4 + 2)
        self.frame_width = unpack("<H", format_chunk.read(2))[0] // 8
        self.frame_cnt = self._data_chunk.size

        # Prepare for playback
        self._data_chunk.seek(0)

    def _enumerate_chunks(self, header: RIFFHeader) -> list[RIFFChunk]:
        """
        Get all RIFF chunks within this file (including their absolute file
        offsets).
        NOTE: This does not parse LIST chunks or any nested chunks.

        :param header: RIFF file header (with all unparsed chunks afterwards)
        :returns: List of all chunks contained inside.
        """

        eof_offset = header.data_offset + header.size - 4
        chunks = []

        while self.wav_file.tell() < eof_offset:
            chunk = RIFFChunk(self.wav_file, self.wav_file.tell())
            chunks.append(chunk)
            chunk.skip()

        return chunks

    def _find_chunk(self, chunks: list[RIFFChunk], tag: bytes) -> RIFFChunk:
        """
        Get a handle to a chunk that was already enumerated before.

        :param chunks: Pre-enumerated chunks list (with offsets already calculated)
        :param tag: Tag of desired chunk.
        :returns: The desired chunk.
        """
        out = [chunk for chunk in chunks if chunk.tag == tag]

        if len(out) == 1:
            return out[0]

        raise ValueError(f"missing chunk {tag}")
    
    def read(self, num_frames: int) -> bytes:
        """
        Read ``num_frames`` frames from the chunk. Each frame is 1 set of samples, so
        2 samples for stereo and 1 for mono. Standard stereo would be 4 bytes per frame.

        :param num_frames: Number of frames to read.
        :returns: Buffer with all read frames.
        """
        return self._data_chunk.read(num_frames * self.frame_width * self.num_channels)
    
    async def read_into(self, buffer: memoryview[int]) -> int:
        """
        Stream frames into the provided buffer. Buffer must a multiple of the frame width.

        :param buffer: Buffer to read into
        :returns: Number of bytes read.
        """
        if not len(buffer) % (self.frame_width * self.num_channels) == 0:
            raise IndexError("bad buffer size")

        return await self._data_chunk.readinto(buffer)
    
    def seek(self, offset: int) -> None:
        """
        Seek within the data region of this file. 0 offset corresponds to the
        beginning of the sample data.

        :param offset: Offset within the sample region
        """
        self._data_chunk.seek(offset)

    def __del__(self):
        self.wav_file.close()
        del self._data_chunk

class RIFFHeader:
    """
    NOTE: Not a compliant RIFF parser by design.

    All chunks have the following format:

    4 bytes: an ASCII identifier for this chunk (examples are "fmt " and "data"; note the space in "fmt ").
    4 bytes: an unsigned, little-endian 32-bit integer with the length of this chunk (except this field itself and the chunk identifier).
    variable-sized field: the chunk data itself, of the size given in the previous field.
    a pad byte, if the chunk's length is not even.
    """
    def __init__(self, in_f):
        self.in_f = in_f
        self.in_f.seek(0)

        if not in_f.read(4) == b"RIFF":
            raise ValueError("bad riff header")
        
        self.size = int.from_bytes(in_f.read(4), "little")

        if not in_f.read(4) == b"WAVE":
            raise ValueError("not wav file")

        self.data_offset = in_f.tell()

class RIFFChunk:
    """
    NOTE: Not a compliant RIFF parser by design.

    All chunks have the following format:

    4 bytes: an ASCII identifier for this chunk (examples are "fmt " and "data"; note the space in "fmt ").
    4 bytes: an unsigned, little-endian 32-bit integer with the length of this chunk (except this field itself and the chunk identifier).
    variable-sized field: the chunk data itself, of the size given in the previous field.
    a pad byte, if the chunk's length is not even.
    """
    def __init__(self, in_f, start_offset: int):
        self.in_f = in_f
        self.in_f.seek(start_offset)

        self.tag = in_f.read(4)        
        self.size = int.from_bytes(in_f.read(4), "little")
        self.data_offset = in_f.tell()

    def skip(self):
        """
        Skip over the rest of this chunk (useful for enumerating chunks).
        """
        self.in_f.seek(self.data_offset + self.size)

    def seek(self, offset: int):
        """
        Seek within this chunk's data region.

        :param offset: Offset within the chunk.
        """
        if offset >= self.size:
            raise IndexError(f"{offset} >= {self.size}")

        self.in_f.seek(self.data_offset + offset)

    def read(self, num_bytes: int) -> bytes:
        """
        Read data within this chunk. If more bytes are requested than are available,
        only what remains within the chunk will be provided.

        :param num_bytes: Number of bytes to read from the chunk
        :returns: The byte data read
        """

        chunk_loc = self.in_f.tell() - self.data_offset

        # bounds check
        if chunk_loc + num_bytes >= self.size:
            num_bytes = self.size - chunk_loc
            #raise IndexError(f"oob read: {chunk_loc} + {num_bytes} > {self.size}")
        
        return self.in_f.read(num_bytes)
    
    async def readinto(self, buffer: memoryview[int]) -> int:
        """
        Read data within this chunk into the buffer provided. Due to the nature
        of wave reading and specific requirements, this function uses asyncio.

        :param buffer: Buffer to dump samples into
        :returns: The number of bytes read.
        """

        chunk_loc = self.in_f.tell() - self.data_offset
        buffer_len = len(buffer)

        # bounds check
        if chunk_loc + buffer_len >= self.size:
            buffer_len = self.size - chunk_loc
            print(f"overread; truncated buffer len to {buffer_len}")

        bytes_read = 0

        chks = buffer_len // _CHK_MAX_READ
        remaining = buffer_len - (chks * _CHK_MAX_READ)
        for chk in range(chks):
            bytes_read += self.in_f.readinto(buffer[chk*_CHK_MAX_READ:(chk+1)*_CHK_MAX_READ])
            await asyncio.sleep_ms(0)
        
        if remaining != 0:
            bytes_read += self.in_f.readinto(buffer[chks*_CHK_MAX_READ:])

        return bytes_read