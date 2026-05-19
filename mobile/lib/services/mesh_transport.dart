import 'dart:async';
import 'dart:typed_data';

/// Connection type for display and logic branching.
enum ConnectionType { ble, tcp, serial }

/// Abstract transport for communicating with a Meshtastic device.
///
/// All three transports (BLE, TCP, Serial) implement this interface.
/// The protocol layer (protobuf encoding/decoding, config read, admin
/// commands, position relay) works identically across transports — only
/// the framing and discovery differ.
abstract class MeshTransport {
  /// The transport type.
  ConnectionType get type;

  /// Human-readable label for the connection
  /// (e.g. "Meshtastic_1234", "192.168.1.50:4403", "CP2102 USB").
  String get connectionLabel;

  /// Whether the transport is currently connected.
  bool get isConnected;

  /// Write a protobuf-encoded ToRadio message to the device.
  Future<void> writeToRadio(Uint8List data);

  /// Read one protobuf-encoded FromRadio message from the device.
  /// Returns an empty [Uint8List] if no data is available.
  Future<Uint8List> readFromRadio();

  /// Stream that fires whenever new data is available to read.
  ///
  /// For BLE this wraps the fromNum notification characteristic.
  /// For TCP/Serial the socket/serial stream always pushes data, so
  /// this fires whenever a complete frame has been buffered.
  ///
  /// May be `null` if the transport doesn't support push notifications
  /// (the caller falls back to polling).
  Stream<void>? get onDataAvailable;

  /// Disconnect and clean up all resources (sockets, subscriptions, etc.).
  Future<void> disconnect();
}
