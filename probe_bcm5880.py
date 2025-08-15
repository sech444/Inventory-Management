#!/usr/bin/env python3
import usb.core
import usb.util

VID = 0x0a5c  # Broadcom vendor ID
PID = 0x5834  # BCM5880 product ID

# Find the device
dev = usb.core.find(idVendor=VID, idProduct=PID)
if dev is None:
    print("Device not found.")
    exit(1)

print(f"Found device: {hex(dev.idVendor)}:{hex(dev.idProduct)}")
print("Configurations and endpoints:")

for cfg in dev:
    print(f" Configuration {cfg.bConfigurationValue}")
    for intf in cfg:
        print(f"  Interface {intf.bInterfaceNumber}, Class: {intf.bInterfaceClass}")
        for ep in intf:
            print(f"   Endpoint: {hex(ep.bEndpointAddress)}, Type: {ep.bmAttributes}, MaxPktSize: {ep.wMaxPacketSize}")

# Try to claim interface 0
intf_num = 0
try:
    if dev.is_kernel_driver_active(intf_num):
        print(" Detaching kernel driver...")
        dev.detach_kernel_driver(intf_num)
    usb.util.claim_interface(dev, intf_num)
    print(" Interface claimed.")

    # Try reading from IN endpoints
    for cfg in dev:
        for intf in cfg:
            for ep in intf:
                if ep.bEndpointAddress & 0x80:  # IN endpoint
                    print(f" Trying read from endpoint {hex(ep.bEndpointAddress)}")
                    try:
                        data = dev.read(ep.bEndpointAddress, ep.wMaxPacketSize, timeout=2000)
                        print("  Read data:", data)
                    except usb.core.USBError as e:
                        print("  Read error:", e)

    usb.util.release_interface(dev, intf_num)
    print(" Interface released.")

except usb.core.USBError as e:
    print("USB error:", e)

print("Done.")

