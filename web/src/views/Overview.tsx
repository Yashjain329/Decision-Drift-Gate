'use client';
// PORT TARGET: legacy/index.html section "overview" + the matching render function in legacy/app.js.
import { View } from '@/components/Shell';
import { Empty, PageHead } from '@/components/ui';

export default function Overview() {
  return (
    <View id="overview" labelledBy="overview-title">
      <PageHead id="overview-title" crumb="Overview" title="Decision integrity" />
      <Empty glyph="overview">Not ported yet.</Empty>
    </View>
  );
}
