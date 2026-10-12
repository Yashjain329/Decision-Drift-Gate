'use client';
// PORT TARGET: legacy/index.html section "checks" + the matching render function in legacy/app.js.
import { View } from '@/components/Shell';
import { Empty, PageHead } from '@/components/ui';

export default function CheckStudio() {
  return (
    <View id="checks" labelledBy="checks-title">
      <PageHead id="checks-title" crumb="Check Studio" title="Does this check prove the decision?" />
      <Empty glyph="checks">Not ported yet.</Empty>
    </View>
  );
}
