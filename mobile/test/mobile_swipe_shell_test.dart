import 'package:flutter_test/flutter_test.dart';

import 'package:aervyx_mobile/screens/mobile_swipe_shell.dart';

void main() {
  test('pilot swipe pages put challenges and logbook right of map', () {
    expect(
      mobileSwipePages(isDriver: false),
      [
        MobileSwipePage.map,
        MobileSwipePage.challenges,
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
        MobileSwipePage.challenges,
        MobileSwipePage.liveView,
        MobileSwipePage.settings,
      ],
    );
  });
}
