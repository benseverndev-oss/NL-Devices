"""Spike step 2 — the same 3-block slice in SKiDL (bake-off vs. atopile).

    5V --[power_block: AMS1117-3.3]--> 3V3 --+--[mcu_block: I2C controller]
                                             +--[sensor_block: 24LC256 EEPROM]
                                                 (I2C bus SCL/SDA shared)

Contrast with the atopile slice: SKiDL "ports" are bare named nets passed
positionally. There is NO typed voltage-domain / I2C contract — nothing checks
that `v3v3` is really 3.3 V or that `scl` is a logic signal referenced to the
rail. That seam-type layer is exactly what we'd have to BUILD on top of SKiDL,
whereas atopile gives it natively. SKiDL's strength is the real pin-level ERC.
"""
import os
from skidl import (Part, Net, ERC, generate_netlist, set_default_tool,
                   subcircuit, POWER, KICAD8)

set_default_tool(KICAD8)

C0402 = 'Capacitor_SMD:C_0402_1005Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
R0402 = 'Resistor_SMD:R_0402_1005Metric'


@subcircuit
def power_block(vin, v3v3, gnd):
    """5V -> 3V3 via AMS1117-3.3 LDO + input/output decoupling."""
    reg = Part('Regulator_Linear', 'AMS1117-3.3',
               footprint='Package_TO_SOT_223:SOT-223-3_TabPin2')
    cin = Part('Device', 'C', value='1uF', footprint=C0402)
    cout = Part('Device', 'C', value='10uF', footprint=C0603)
    reg['VI'] += vin
    reg['VO'] += v3v3
    reg['GND'] += gnd
    cin[1] += vin;  cin[2] += gnd
    cout[1] += v3v3; cout[2] += gnd


@subcircuit
def mcu_block(v3v3, gnd, scl, sda):
    """I2C controller side: decoupling + bus pull-ups to the 3V3 rail."""
    cdec = Part('Device', 'C', value='100nF', footprint=C0402)
    rscl = Part('Device', 'R', value='4.7k', footprint=R0402)
    rsda = Part('Device', 'R', value='4.7k', footprint=R0402)
    cdec[1] += v3v3; cdec[2] += gnd
    rscl[1] += scl;  rscl[2] += v3v3
    rsda[1] += sda;  rsda[2] += v3v3
    # A real MCU IC would attach here; modeled as the bus controller for the slice.


@subcircuit
def sensor_block(v3v3, gnd, scl, sda):
    """I2C peripheral: 24LC256 EEPROM (address 0x50) + decoupling."""
    eep = Part('Memory_EEPROM', '24LC256',
               footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm')
    cdec = Part('Device', 'C', value='100nF', footprint=C0402)
    eep['VCC'] += v3v3
    eep['GND'] += gnd
    eep['SCL'] += scl
    eep['SDA'] += sda
    eep['A0', 'A1', 'A2'] += gnd   # address pins low -> 0x50
    eep['WP'] += gnd               # write-protect off
    cdec[1] += v3v3; cdec[2] += gnd


# --- compose the three blocks over shared nets (the "seams") ---------------
vin5, v3v3, gnd = Net('5V'), Net('3V3'), Net('GND')
scl, sda = Net('SCL'), Net('SDA')

# Board-edge supplies have no on-board driver symbol -> mark them as power
# sources (the SKiDL equivalent of a KiCad PWR_FLAG) so pin-level ERC is clean.
vin5.drive = POWER
gnd.drive = POWER

power_block(vin5, v3v3, gnd)
mcu_block(v3v3, gnd, scl, sda)
sensor_block(v3v3, gnd, scl, sda)

ERC()
generate_netlist(file_='sensor_node.net')
print("PASS: SKiDL 3-block slice built; ERC ran; wrote sensor_node.net")
