import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';

class AppMapScaleBar extends StatelessWidget {
  final EdgeInsets padding;

  const AppMapScaleBar({
    super.key,
    this.padding = const EdgeInsets.only(left: 12, bottom: 12),
  });

  @override
  Widget build(BuildContext context) {
    return Scalebar(
      alignment: Alignment.bottomLeft,
      padding: padding,
      lineColor: Colors.black87,
      textStyle: const TextStyle(
        color: Colors.black87,
        fontSize: 12,
        fontWeight: FontWeight.w600,
        shadows: [
          Shadow(color: Colors.white, blurRadius: 3),
          Shadow(color: Colors.white, blurRadius: 3),
        ],
      ),
    );
  }
}
