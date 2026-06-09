# Hello-world: SKiDL builds a 5V divider, runs ERC, emits a KiCad netlist.
import os
from skidl import Part, Net, ERC, generate_netlist, set_default_tool, KICAD8

set_default_tool(KICAD8)

vin, mid, gnd = Net('VIN'), Net('MID'), Net('GND')
r1 = Part('Device', 'R', value='10k', footprint='Resistor_SMD:R_0402_1005Metric')
r2 = Part('Device', 'R', value='10k', footprint='Resistor_SMD:R_0402_1005Metric')
vin += r1[1]
mid += r1[2], r2[1]
gnd += r2[2]

ERC()
generate_netlist(file_='divider.net')
print("PASS: SKiDL built circuit, ran ERC, wrote divider.net")
