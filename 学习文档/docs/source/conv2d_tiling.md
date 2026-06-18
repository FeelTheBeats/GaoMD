Analysis of 19 Valid Overflow Flags and Split Strategies:
-------------------------------------------------------------------------
Flag(Hex) | Description             | Strategy(3bit) | Logic Explanation
-------------------------------------------------------------------------
0x40      | TotalSum                | H (4)          | Default spatial split (Cost efficient)
0x48      | I+W                     | IC (2)         | Only IC reduces (IFM + WGT)
0x50      | I+O                     | H (4)          | Default spatial split (Cost efficient)
0x58      | I+W I+O                 | IC (2)         | Only IC reduces (IFM + WGT)
0x59      | IFM                     | H (4)          | Fix IFM overflow -> Split H
0x60      | W+O                     | H (4)          | Default spatial split (Cost efficient)
0x68      | I+W W+O                 | IC (2)         | Only IC reduces (IFM + WGT)
0x6a      | WGT                     | OC (1)         | Fix WGT or OFM -> Split OC
0x70      | I+O W+O                 | H (4)          | Default spatial split (Cost efficient)
0x74      | OFM                     | OC (1)         | Fix WGT or OFM -> Split OC
0x78      | I+W I+O W+O             | IC (2)         | Only IC reduces (IFM + WGT)
0x79      | IFM                     | H (4)          | Fix IFM overflow -> Split H
0x7a      | WGT                     | OC (1)         | Fix WGT or OFM -> Split OC
0x7b      | IFM WGT                 | OC H (5)       | IFM&WGT both big -> Split H & OC
0x7c      | OFM                     | OC (1)         | Fix WGT or OFM -> Split OC
0x7d      | IFM OFM                 | H (4)          | Fix IFM overflow -> Split H
0x7e      | WGT OFM                 | OC (1)         | Fix WGT or OFM -> Split OC
0x7f      | IFM WGT OFM             | OC H (5)       | IFM&WGT both big -> Split H & OC
