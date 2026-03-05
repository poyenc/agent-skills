# Hardware Specs Table

## What it is

Consolidated specifications for all AMD Instinct MI300/MI350 series GPUs. Use this
as a quick-reference for concrete numbers when calculating occupancy, roofline
analysis, or comparing architectures.

## Consolidated specs

| Spec                       | MI300X    | MI300A      | MI325X    | MI350X     | MI355X     |
|----------------------------|-----------|-------------|-----------|------------|------------|
| **Architecture**           | CDNA3     | CDNA3       | CDNA3     | CDNA4      | CDNA4      |
| **ISA target**             | gfx942    | gfx940      | gfx942    | gfx950     | gfx950     |
| **Process**                | 5nm+6nm   | 5nm+6nm     | 5nm+6nm   | 3nm+6nm    | 3nm+6nm    |
| **CUs**                    | 304       | 228         | 304       | 256        | 256        |
| **XCDs**                   | 8         | 6           | 8         | 8          | 8          |
| **CUs/XCD**                | 38        | 38          | 38        | 32         | 32         |
| **SIMDs/CU**               | 4         | 4           | 4         | 4          | 4          |
| **Matrix cores/CU**        | 4         | 4           | 4         | 4          | 4          |
| **Stream processors**      | 19,456    | 14,592      | 19,456    | 16,384     | 16,384     |
| **Peak clock (MHz)**       | 2,100     | 2,100       | 2,100     | 2,200      | 2,400      |
|                            |           |             |           |            |            |
| **HBM type**               | HBM3     | HBM3        | HBM3E    | HBM3E      | HBM3E      |
| **HBM capacity**           | 192 GB    | 128 GB      | 256 GB    | 288 GB     | 288 GB     |
| **HBM bandwidth**          | 5.3 TB/s  | 5.3 TB/s    | 6.0 TB/s  | 8.0 TB/s   | 8.0 TB/s   |
| **Memory interface**       | 8192-bit  | 8192-bit    | 8192-bit  | 8192-bit   | 8192-bit   |
| **L2 total**               | 256 MB    | 192 MB      | 256 MB    | 256 MB     | 256 MB     |
| **L2 per XCD**             | 4 MB      | 4 MB        | 4 MB      | 4 MB       | 4 MB       |
| **L1 per CU**              | 32 KB     | 32 KB       | 32 KB     | 32 KB      | 32 KB      |
| **LDS per CU**             | 64 KB     | 64 KB       | 64 KB     | 64 KB      | 64 KB      |
|                            |           |             |           |            |            |
| **Peak FP16 (TFLOPS)**     | 1,307     | 981         | 1,307     | 2,310      | 2,517      |
| **Peak BF16 (TFLOPS)**     | 1,307     | 981         | 1,307     | 2,310      | 2,517      |
| **Peak FP8 (TFLOPS)**      | 2,615     | 1,961       | 2,615     | 4,614      | 5,033      |
| **Peak FP4 (TFLOPS)**      | N/A       | N/A         | N/A       | 9,228      | 10,066     |
| **Peak FP32 vec (TFLOPS)** | 163       | 123         | 163       | 144        | 157        |
| **Peak FP64 vec (TFLOPS)** | 82        | 61          | 82        | 72         | 79         |
| **Peak FP64 mat (TFLOPS)** | 163       | 123         | 163       | 72         | 79         |
|                            |           |             |           |            |            |
| **With 2:4 sparsity**      |           |             |           |            |            |
| **FP16 sparse (TFLOPS)**   | 2,615     | 1,961       | 2,615     | 4,619      | 5,033      |
| **FP8 sparse (TFLOPS)**    | 5,230     | 3,922       | 5,230     | 9,227      | 10,066     |
|                            |           |             |           |            |            |
| **TDP**                    | 750W      | 550-760W    | 1,000W    | 1,000W     | 1,400W     |
| **IF links (per GPU)**     | 7×128 GB/s| 4×128 GB/s  | 7×128 GB/s| 7×154 GB/s | 7×154 GB/s |
| **PCIe**                   | Gen5 ×16  | Gen5 ×16    | Gen5 ×16  | Gen5 ×16   | Gen5 ×16   |

## Key architectural notes

### FP64 matrix rate difference
```
CDNA3: FP64 matrix rate = FP32 matrix rate (full-rate FP64)
  → MI300X: 163 FP64 matrix TFLOPS

CDNA4: FP64 matrix rate = FP64 vector rate (half-rate FP64 matrix)
  → MI350X: 72 FP64 matrix TFLOPS

CDNA4 trades FP64 matrix throughput for massively higher low-precision (FP8/FP4).
For HPC requiring FP64 MFMA: CDNA3 (MI300X) is 2.3× faster per instruction.
```

### CDNA4 new data types
```
MXFP8:  OCP-standardized FP8 with block scaling (E8M0 shared exponent per 32 elements)
MXFP6:  E2M3 and E3M2 element formats with block scaling
MXFP4:  E2M1 element format with block scaling
These deliver 2-4× TFLOPS vs FP16 while maintaining useful precision via shared exponents.
```

### Derived metrics

| Metric (FP16)          | MI300X    | MI350X    | MI355X    |
|------------------------|-----------|-----------|-----------|
| Ridge point (FLOP/B)   | 247       | 289       | 315       |
| TFLOPS/Watt            | 1.74      | 2.31      | 1.80      |
| TFLOPS/GB HBM          | 6.8       | 8.0       | 8.7       |

## Sources

- MI300X datasheet: `pdfs/mi300x-accelerator-datasheet.pdf`
- MI300A datasheet: `pdfs/mi300a-apu-datasheet.pdf`
- MI325X datasheet: `pdfs/mi325x-accelerator-datasheet.pdf`
- MI350X datasheet: `pdfs/mi350x-gpu-datasheet.pdf`
- MI355X datasheet: `pdfs/mi355x-gpu-datasheet.pdf`
