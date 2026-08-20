#!/bin/sh
set -eu

# NVIDIA's default Vulkan ICD (libGLX_nvidia.so.0) reliably fails to initialize inside this
# host's Docker containers -- vk_icdGetInstanceProcAddr returns NULL for vkCreateInstance --
# even though the ICD manifest, injected driver library, /proc/driver/nvidia, and device nodes
# are all confirmed byte-identical to the host (research.md #11). NVIDIA's own driver docs
# recommend the EGL-backed ICD (libEGL_nvidia.so.0) for exactly this case ("environments where
# X11 client libraries are not available") -- confirmed fixed (research.md #12): identical
# container, only the ICD's library_path swapped, and libplacebo/Vulkan initializes and
# encodes correctly in a completely ordinary, non-privileged container.
#
# The real /etc/vulkan/icd.d/nvidia_icd.json only exists once the NVIDIA Container Toolkit
# injects it at container start (GPU capability granted) -- can't bake a replacement into the
# image at build time, and can't overwrite it in place (it's a read-only bind mount). So this
# runs at container start: copy the toolkit's own injected manifest, swap the ICD library, and
# point the Vulkan loader at the copy via VK_DRIVER_FILES.
if [ -f /etc/vulkan/icd.d/nvidia_icd.json ]; then
  sed 's/libGLX_nvidia\.so\.0/libEGL_nvidia.so.0/' /etc/vulkan/icd.d/nvidia_icd.json \
    > /tmp/nvidia_egl_icd.json
  export VK_DRIVER_FILES=/tmp/nvidia_egl_icd.json
fi

exec "$@"
