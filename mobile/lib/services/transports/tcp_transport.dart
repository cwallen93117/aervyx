import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import '../mesh_transport.dart';
import 'framed_transport_mixin.dart';

/// Default Meshtastic TCP API port.
const int defaultMeshtasticTcpPort = 4403;

/// TCP transport for Meshtastic devices with WiFi enabled.
///
/// Connects to the device's IP on port 4403 (configurable). Uses the
/// standard Meshtastic 4-byte frame header shared with serial:
///   `[0x94][0xC3][length_MSB][length_LSB][protobuf_data]`
class TcpTransport with FramedTransportMixin implements MeshTransport {
  final String host;
  final int port;

  Socket? _socket;
  StreamSubscription<Uint8List>? _socketSubscription;
  bool _connected = false;

  TcpTransport({required this.host, this.port = defaultMeshtasticTcpPort});

  /// Connect to the device.  Call this before any read/write.
  Future<void> connect({Duration timeout = const Duration(seconds: 10)}) async {
    _socket = await Socket.connect(host, port, timeout: timeout);
    _connected = true;

    _socketSubscription = _socket!.listen(
      (data) => feedBytes(data),
      onError: (_) => _handleDisconnect(),
      onDone: () => _handleDisconnect(),
      cancelOnError: false,
    );
  }

  void _handleDisconnect() {
    _connected = false;
    _socketSubscription?.cancel();
    _socketSubscription = null;
    _socket = null;
  }

  @override
  ConnectionType get type => ConnectionType.tcp;

  @override
  String get connectionLabel => '$host:$port';

  @override
  bool get isConnected => _connected;

  @override
  Future<void> writeToRadio(Uint8List data) async {
    if (_socket == null) throw Exception('TCP not connected');
    _socket!.add(frameData(data));
    await _socket!.flush();
  }

  @override
  Future<Uint8List> readFromRadio() async {
    // Return next queued frame, or wait briefly for one to arrive.
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
    _socketSubscription?.cancel();
    _socketSubscription = null;
    try {
      _socket?.destroy();
    } catch (_) {}
    _socket = null;
    disposeFraming();
  }
}
