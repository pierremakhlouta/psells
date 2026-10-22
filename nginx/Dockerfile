# PSells' nginx: the pinned official nginx image with Alpine's security fixes
# for the packages it carries, before nginx has rebuilt it with them.
#
# In October 2026 the newest nginx images still carried pcre2 10.48 and zlib
# 1.3.2-r0, each with a high-severity flaw, and OpenSSL 3.5.8, when Alpine 3.24
# already had pcre2 10.49, zlib 1.3.2-r1 and OpenSSL 3.5.9. Building on the
# pinned image and upgrading those packages, and only those, keeps nginx
# itself exactly as published while the scan in image.yml passes without
# exceptions. --no-cache leaves no package index in the image. Remove a name
# once the pinned image has its fix.
#
# Nothing is copied in: nginx's configuration stays in this folder, mounted
# read-only by compose.yaml, as before. CI builds, scans and publishes this
# image beside the app's, as ghcr.io/pierremakhlouta/psells:nginx-<commit>.
# Dependabot watches the FROM line.
FROM nginx:1.30.6-alpine-slim@sha256:d9322bba63c6cfc63dc9e86522fd4f95fd4d9020a02b5bced282bbf38b8c3960

RUN apk upgrade --no-cache zlib pcre2 libssl3 libcrypto3
