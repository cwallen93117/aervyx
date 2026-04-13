import 'dart:async';
import 'dart:typed_data';

import 'package:usb_serial/usb_serial.dart';

import '../mesh_transport.dart';
import 'framed_transport_mixin.dart';

/// USB Serial (OTG) transport for Meshtastic devices.
///
/// Uses the same 4-byte frame header as TCP:
///   `[0x94][0xC3][length_MSB][length_LSB][protobuf_data]`
///
/// Baud rate defaults to 115200 (Meshtastic standard).
/// Android only — iOS does not support USB host-mode serial.
class SerialTransport with FramedTransportMixin implements MeshTransport {
  final UsbDevice usbDevice;
  final int baudRate;

  UsbPort? _port;
  StreamSubscription<Uint8List>? _portSubscription;
  bool _connected = false;

  SerialTransport({
    required this.usbDevice,
    this.baudRate = 115200,
  });

  /// Open the serial port and begin listening.  Call before read/write.
  Future<void> connect() async {
    _port = (await usbDevice.create())!;

    final opened = await _port!.open();
    if (!opened) throw Exception('Failed to open USB serial port');

    await _port!.setDTR(true);
    await _port!.setRTS(true);
    await _port!.setPortParameters(
      baudRate,
      UsbPort.DATABITS_8,
      UsbPort.STOPBITS_1,
      UsbPort.PARITY_NONE,
    );

    _connected = true;

    _portSubscription = _port!.inputStream?.listen(
      (data) => feedBytes(data),
      onError: (_) => _handleDisconnect(),
      onDone: () => _handleDisconnect(),
      cancelOnError: false,
    );
  }

  void _handleDisconnect() {
    _connected = false;
    _portSubscription?.cancel();
    _portSubscription = null;
    _port = null;
  }

  @override
  ConnectionType get type => ConnectionType.serial;

  @override
  String get connectionLabel =>
      usbDevice.productName ?? 'USB Serial #${usbDevice.deviceId}';

  @override
  bool get isConnected => _connected;

  @override
  Future<void> writeToRadio(Uint8List data) async {
    if (_port == null) throw Exception('Serial not connected');
    await _port!.write(frameData(data));
  }

  @override
  Future<Uint8List> readFromRadio() async {
    if (hasQueuedFrames) return nextFrame();

    // Wait up to 200ms for a frame
    final completer = Completer<Uint8List>();
    StreamSubscription<void>? sub;
    Timer? timer;

    sub = frameDataAvailable.listen((_) {
      if (!completer.isCompleted) {
        timer?.cancel();
        sub?.cancel();
        completer.complete(nextFrame());
      }
    });

    timer = Timer(const Duration(milliseconds: 200), () {
      sub?.cancel();
      if (!completer.isCompleted) {
        completer.complete(Uint8List(0));
      }
    });

    return completer.future;
  }

  @override
  Stream<void>? get onDataAvailable => frameDataAvailable;

  @override
  Future<void> disconnect() async {
    _connected = false;
    _portSubscription?.cancel();
    _portSubscription = null;
    try {
      await _port?.close();
    } catch (_) {}
    _port = null;
    disposeFraming();
  }
}
