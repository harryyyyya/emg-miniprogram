const ARTICLES = {
  1: {
    tag: 'Connection',
    title: 'First connection checklist for ESP32 hand',
    summary: 'Use this checklist when the mini program cannot show the ESP32 hand online.',
    sections: [
      {
        heading: '1. Check firmware settings',
        items: [
          'BACKEND_HOST should be 47.239.150.223.',
          'BACKEND_PORT should be 80.',
          'HARDWARE_ID should match the mini program binding value.',
          'BOARD_TOKEN should match the device token in the mini program.',
        ],
      },
      {
        heading: '2. Check serial monitor',
        items: [
          'Set serial baud rate to 115200.',
          'Wait for WiFi connected, IP=...',
          'registerBoard status=200 means the device is registered.',
          'heartbeat status=200 means the cloud backend sees the device online.',
        ],
      },
      {
        heading: '3. Check mini program status',
        items: [
          'Bind the default device ESP32-HAND-001 if you use the current firmware.',
          'Open the control page and tap refresh device status.',
          'If it is still offline, compare HARDWARE_ID and BOARD_TOKEN again.',
        ],
      },
    ],
    tips: [
      'Binding success only means the backend saved device info. Online status depends on ESP32 heartbeat.',
      'If you change to another board, burn the same firmware or update the device id and token together.',
    ],
  },
  2: {
    tag: 'Training',
    title: 'How to record stable gesture EMG data',
    summary: 'Stable posture and repeatable timing are more important than recording for a very long time.',
    sections: [
      {
        heading: '1. Prepare before recording',
        items: [
          'Keep the armband position fixed before each session.',
          'Make sure the Bluetooth armband status is online.',
          'Rest the hand for a few seconds before tapping start.',
        ],
      },
      {
        heading: '2. During each 5-second gesture',
        items: [
          'Hold one gesture steadily instead of changing force quickly.',
          'Avoid moving the arm too much while recording.',
          'Watch the raw EMG waveform. A stable gesture should have visible but not clipped changes.',
        ],
      },
      {
        heading: '3. After recording',
        items: [
          'Check RMS, peak, min and max values for abnormal jumps.',
          'Delete poor sessions and record again if the signal is flat or heavily clipped.',
          'Record multiple clean sessions for the same gesture before model training.',
        ],
      },
    ],
    tips: [
      'Short stable samples are usually better than long noisy samples.',
      'If recognition is unstable, first improve data quality before changing the model.',
    ],
  },
};

Page({
  data: {
    article: null,
  },

  onLoad(options) {
    const id = Number(options.id || 1);
    this.setData({ article: ARTICLES[id] || ARTICLES[1] });
  },
});
