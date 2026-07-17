import 'package:flutter_test/flutter_test.dart';

import 'package:aervyx_mobile/screens/mobile_swipe_shell.dart';

void main() {
  test('pilot swipe pages put events and logbook right of map', () {
    expect(
      mobileSwipePages(isDriver: false),
      [
        MobileSwipePage.map,
        MobileSwipePage.events,
        MobileSwipePage.logbook,
        MobileSwipePage.liveView,
        MobileSwipePage.settings,
      ],
    );
  });

  test('driver swipe pages omit logbook and include live view', () {
    expect(
      mobileSwipePages(isDriver: true),
      [
        MobileSwipePage.map,
        MobileSwipePage.events,
        MobileSwipePage.liveView,
        MobileSwipePage.settings,
      ],
    );
  });
}
