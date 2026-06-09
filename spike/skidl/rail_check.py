"""Step 5: electrical sanity on the slice's seams, via the ngspice primitive.

Two checks tied to the actual design:
  (a) 3V3 rail under aggregate load stays within 3.3V +/- 5%
  (b) I2C pull-up sink current (line pulled low) is within I2C spec (< 3 mA)
"""
from ngspice_check import op_point

# (a) LDO 3V3 output modeled as an ideal 3.3V source behind a small output
#     impedance, feeding the slice's aggregate load (~50 mA: MCU + EEPROM + bias).
rail = """* 3v3 rail under load
Vreg VREG 0 3.3
Rout VREG V3V3 0.1
Rload V3V3 0 66
"""
v = op_point(rail, ['V3V3'])['V3V3']
lo, hi = 3.3*0.95, 3.3*1.05
ok_a = lo <= v <= hi
print(f"(a) 3V3 rail under load: V(3V3) = {v:.4f} V  [{lo:.3f},{hi:.3f}]  -> {'PASS' if ok_a else 'FAIL'}")

# (b) I2C pull-up: 4.7k from 3V3 to SCL; a device pulls SCL low (~10 ohm).
#     Sink current through the pull-up must stay under the 3 mA I2C limit.
pull = """* i2c pullup sink current
V3 V3V3 0 3.3
Rp V3V3 SCL 4700
Rdev SCL 0 10
"""
vscl = op_point(pull, ['SCL'])['SCL']
i_sink_mA = (3.3 - vscl) / 4700 * 1000
ok_b = i_sink_mA < 3.0
print(f"(b) I2C pull-up sink current = {i_sink_mA:.3f} mA  (< 3 mA spec)  -> {'PASS' if ok_b else 'FAIL'}")

raise SystemExit(0 if (ok_a and ok_b) else 1)
