// usb_descriptors.c
#include "tusb.h"
#include <string.h>

// --- Device identity: HORI Pokken Controller (as used by Switch-Fightstick) ---
#define USB_VID   0x0F0D
#define USB_PID   0x0092
#define USB_BCD   0x0100

static const uint8_t hid_report_desc[] = {
  0x05, 0x01,        // Usage Page (Generic Desktop)
  0x09, 0x05,        // Usage (Joystick)
  0xA1, 0x01,        // Collection (Application)

  // Buttons (16)
  0x15, 0x00,
  0x25, 0x01,
  0x35, 0x00,
  0x45, 0x01,
  0x75, 0x01,
  0x95, 0x10,
  0x05, 0x09,
  0x19, 0x01,
  0x29, 0x10,
  0x81, 0x02,

  // Hat switch (4 bits) + 4 bits padding
  0x05, 0x01,
  0x25, 0x07,
  0x46, 0x3B, 0x01,
  0x75, 0x04,
  0x95, 0x01,
  0x65, 0x14,
  0x09, 0x39,
  0x81, 0x42,
  0x65, 0x00,
  0x95, 0x01,
  0x81, 0x01,

  // 4 axes (X,Y,Z,Rz) 8-bit each
  0x26, 0xFF, 0x00,
  0x46, 0xFF, 0x00,
  0x09, 0x30,
  0x09, 0x31,
  0x09, 0x32,
  0x09, 0x35,
  0x75, 0x08,
  0x95, 0x04,
  0x81, 0x02,

  // Vendor byte (1)
  0x06, 0x00, 0xFF,
  0x09, 0x20,
  0x95, 0x01,
  0x81, 0x02,

  // Output report (8 bytes) required
  0x09, 0x21,
  0x95, 0x08,
  0x91, 0x02,

  0xC0
};

uint8_t const * tud_hid_descriptor_report_cb(uint8_t instance) {
  (void)instance;
  return hid_report_desc;
}

uint16_t tud_hid_get_report_cb(uint8_t instance, uint8_t report_id,
                               hid_report_type_t report_type,
                               uint8_t* buffer, uint16_t reqlen) {
  (void)instance; (void)report_id; (void)report_type;
  memset(buffer, 0, reqlen);
  return reqlen;
}

void tud_hid_set_report_cb(uint8_t instance, uint8_t report_id,
                           hid_report_type_t report_type,
                           uint8_t const* buffer, uint16_t bufsize) {
  (void)instance; (void)report_id; (void)report_type;
  (void)buffer; (void)bufsize;
}

// --- USB descriptors ---
tusb_desc_device_t const desc_device = {
  .bLength            = sizeof(tusb_desc_device_t),
  .bDescriptorType    = TUSB_DESC_DEVICE,
  .bcdUSB             = 0x0200,

  .bDeviceClass       = 0x00,
  .bDeviceSubClass    = 0x00,
  .bDeviceProtocol    = 0x00,

  .bMaxPacketSize0    = CFG_TUD_ENDPOINT0_SIZE,

  .idVendor           = USB_VID,
  .idProduct          = USB_PID,
  .bcdDevice          = USB_BCD,

  .iManufacturer      = 0x01,
  .iProduct           = 0x02,
  .iSerialNumber      = 0x00,

  .bNumConfigurations = 0x01
};

uint8_t const * tud_descriptor_device_cb(void) {
  return (uint8_t const *) &desc_device;
}

enum {
  ITF_NUM_HID = 0,
  ITF_NUM_TOTAL
};

#define EPNUM_HID   0x81
#define EPSIZE_HID  0x40

uint8_t const desc_configuration[] = {
  TUD_CONFIG_DESCRIPTOR(1, ITF_NUM_TOTAL, 0, (TUD_CONFIG_DESC_LEN + TUD_HID_DESC_LEN), 0x80, 250),
  TUD_HID_DESCRIPTOR(ITF_NUM_HID, 0, HID_ITF_PROTOCOL_NONE,
                     sizeof(hid_report_desc), EPNUM_HID, EPSIZE_HID, 5),
};

uint8_t const * tud_descriptor_configuration_cb(uint8_t index) {
  (void)index;
  return desc_configuration;
}

static const char* string_desc_arr[] = {
  (const char[]) { 0x09, 0x04 },
  "HORI CO.,LTD.",
  "POKKEN CONTROLLER",
};

static uint16_t _desc_str[32];

uint16_t const* tud_descriptor_string_cb(uint8_t index, uint16_t langid) {
  (void)langid;

  uint8_t chr_count;

  if (index == 0) {
    memcpy(&_desc_str[1], string_desc_arr[0], 2);
    chr_count = 1;
  } else {
    if (index >= sizeof(string_desc_arr)/sizeof(string_desc_arr[0])) return NULL;
    const char* str = string_desc_arr[index];
    chr_count = (uint8_t) strlen(str);
    if (chr_count > 31) chr_count = 31;
    for (uint8_t i = 0; i < chr_count; i++) _desc_str[1 + i] = (uint16_t) str[i];
  }

  _desc_str[0] = (TUSB_DESC_STRING << 8) | (2 * chr_count + 2);
  return _desc_str;
}
