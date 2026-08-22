#ifndef NETWORK_WORKER_H
#define NETWORK_WORKER_H

#include <stdint.h>

void network_worker_begin(bool enable_emg_upload);
void network_worker_poll_once_for_wifi_only(void);

#endif
