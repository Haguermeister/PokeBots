cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(shinybot_uart_fw C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(shinybot_uart_fw
  src/main.c
  src/usb_descriptors.c
)

target_include_directories(shinybot_uart_fw PRIVATE src)

target_link_libraries(shinybot_uart_fw
  pico_stdlib
  hardware_uart
  pico_cyw43_arch_none
  tinyusb_device
  tinyusb_board
)

# Don't fight TinyUSB by also using USB stdio
pico_enable_stdio_usb(shinybot_uart_fw 0)
pico_enable_stdio_uart(shinybot_uart_fw 0)

pico_add_extra_outputs(shinybot_uart_fw)
