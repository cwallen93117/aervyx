import 'dart:async';
import 'dart:collection';
import 'dart:typed_data';

/// Meshtastic TCP/Serial frame magic bytes.
const int _frameMagicHi = 0x94;
const int _frameMagicLo = 0xC3;

/// Shared framing logic for TCP and Serial transports.
///
/// Both transports wrap protobuf payloads in a 4-byte header:
///   `[0x94][0xC3][length_MSB][length_LSB][protobuf_data]`
///
/// This mixin provides:
/// - [frameData] — wraps a protobuf payload for writing
/// - [feedBytes] — accepts raw bytes from the socket/serial stream,
///   accumulates them in a buffer, and extracts complete frames
/// - [nextFrame] — dequeues the next complete protobuf payload
mixin FramedTransportMixin {
  final List<int> _receiveBuffer = [];
  final Queue<Uint8List> _frameQueue = Queue<Uint8List>();
  final StreamController<void> _dataAvailableController =
      StreamController<void>.broadcast();

  /// Stream that fires whenever a complete frame has been buffered
  /// and is ready to be read via [nextFrame].
  Stream<void> get frameDataAvailable => _dataAvailableController.stream;

  /// Wrap a protobuf payload in the 4-byte Meshtastic frame header.
  Uint8List frameData(Uint8List protobuf) {
    final length = protobuf.length;
    final frame = Uint8List(4 + length);
    frame[0] = _frameMagicHi;
    frame[1] = _frameMagicLo;
    frame[2] = (length >> 8) & 0xFF; // MSB
    frame[3] = length & 0xFF; // LSB
    frame.setRange(4, 4 + length, protobuf);
    return frame;
  }

  /// Feed raw bytes from the socket/serial stream into the receive
  /// buffer.  Complete frames are extracted and queued automatically.
  void feedBytes(List<int> data) {
    _receiveBuffer.addAll(data);
    _extractFrames();
  }

  /// Extract as many complete frames as possible from the receive buffer.
  void _extractFrames() {
    while (_receiveBuffer.length >= 4) {
      // Scan for magic bytes — resync if corrupted
      if (_receiveBuffer[0] != _frameMagicHi ||
          _receiveBuffer[1] != _frameMagicLo) {
        // Drop bytes until we find the magic header or run out
        int idx = 1;
        while (idx < _receiveBuffer.length - 1) {
          if (_receiveBuffer[idx] == _frameMagicHi &&
              _receiveBuffer[idx + 1] == _frameMagicLo) {
            break;
          }
          idx++;
        }
        _receiveBuffer.removeRange(0, idx);
        continue;
      }

      final length = (_receiveBuffer[2] << 8) | _receiveBuffer[3];
      if (length == 0 || length > 65535) {
        // Invalid length — skip this header and resync
        _receiveBuffer.removeRange(0, 2);
        continue;
      }

      if (_receiveBuffer.length < 4 + length) {
        break; // incomplete frame — wait for more data
      }

      final payload = Uint8List.fromList(
        _receiveBuffer.sublist(4, 4 + length),
      );
      _receiveBuffer.removeRange(0, 4 + length);
      _frameQueue.add(payload);
      _dataAvailableController.add(null);
    }
  }

  /// Dequeue the next complete protobuf frame, or return an empty
  /// [Uint8List] if none is available.
  Uint8List nextFrame() {
    if (_frameQueue.isEmpty) return Uint8List(0);
    return _frameQueue.removeFirst();
  }

  /// Whether there are queued frames ready to read.
  bool get hasQueuedFrames => _frameQueue.isNotEmpty;

  /// Dispose of the mixin's resources.
  void disposeFraming() {
    _receiveBuffer.clear();
    _frameQueue.clear();
    _dataAvailableController.close();
  }
}
