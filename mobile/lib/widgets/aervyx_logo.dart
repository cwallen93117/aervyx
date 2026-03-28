import 'package:flutter/material.dart';

/// The Aervyx logo — cyan triangle with center waypoint, matching the
/// marketing site at aervyx.net.
class AervyxLogo extends StatelessWidget {
  final double size;
  final bool showWordmark;

  const AervyxLogo({super.key, this.size = 80, this.showWordmark = true});

  static const Color cyan = Color(0xFF00E5FF);

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        CustomPaint(
          size: Size(size, size),
          painter: _AervyxLogoPainter(),
        ),
        if (showWordmark) ...[
          SizedBox(height: size * 0.15),
          Text(
            'Aervyx',
            style: TextStyle(
              fontSize: size * 0.35,
              fontWeight: FontWeight.w700,
              color: cyan,
              letterSpacing: 1.2,
            ),
          ),
        ],
      ],
    );
  }
}

class _AervyxLogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;

    // Triangle: top center → bottom-right → bottom-left → back to top
    // with a notch at bottom-center (kite/arrow shape)
    final trianglePath = Path()
      ..moveTo(w * 0.5, h * 0.08) // top
      ..lineTo(w * 0.92, h * 0.88) // bottom-right
      ..lineTo(w * 0.5, h * 0.66) // bottom-center notch
      ..lineTo(w * 0.08, h * 0.88) // bottom-left
      ..close();

    // Stroke the triangle
    final strokePaint = Paint()
      ..color = AervyxLogo.cyan
      ..style = PaintingStyle.stroke
      ..strokeWidth = w * 0.03
      ..strokeJoin = StrokeJoin.round;

    canvas.drawPath(trianglePath, strokePaint);

    // Center line (subtle)
    final linePaint = Paint()
      ..color = AervyxLogo.cyan.withAlpha(100)
      ..style = PaintingStyle.stroke
      ..strokeWidth = w * 0.015;

    canvas.drawLine(
      Offset(w * 0.5, h * 0.08),
      Offset(w * 0.5, h * 0.66),
      linePaint,
    );

    // Center waypoint circle (filled)
    final dotPaint = Paint()
      ..color = AervyxLogo.cyan.withAlpha(220)
      ..style = PaintingStyle.fill;

    canvas.drawCircle(Offset(w * 0.5, h * 0.44), w * 0.065, dotPaint);

    // Outer ring around waypoint (subtle)
    final ringPaint = Paint()
      ..color = AervyxLogo.cyan.withAlpha(55)
      ..style = PaintingStyle.stroke
      ..strokeWidth = w * 0.012;

    canvas.drawCircle(Offset(w * 0.5, h * 0.44), w * 0.14, ringPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
