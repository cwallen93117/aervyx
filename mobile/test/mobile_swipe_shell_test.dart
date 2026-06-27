import 'package:flutter_test/flutter_test.dart';

import 'package:aervyx_mobile/screens/mobile_swipe_shell.dart';

void main() {
  test('pilot swipe pages include map, logbook, challenges, and settings', () {
    expect(
      mobileSwipePages(isDriver: false),
      [
        MobileSwipePage.map,
        MobileSwipePage.logbook,
        MobileSwipePage.challenges,
        MobileSwipePage.settings,
      ],
    );
  });

  test('driver swipe pages omit the logbook and never include shutdown', () {
    expect(
      mobileSwipePages(isDriver: true),
      [
        MobileSwipePage.map,
        MobileSwipePage.challenges,
        MobileSwipePage.settings,
      ],
    );
  });
}
