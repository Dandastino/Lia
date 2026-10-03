import { FlatList, RefreshControl, ScrollView, Text, View } from 'react-native';
import { Banner, Button } from '../../components/ui';
import { colors } from '../../theme';
import { styles } from '../AdminScreen.styles';

const refreshControl = (refreshing, onRefresh) => (
  <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} colors={[colors.primary]} />
);

export function DashboardTab({ organizations, users, loading, loadError, onRefresh }) {
  return (
    <ScrollView contentContainerStyle={styles.tabContent} refreshControl={refreshControl(loading, onRefresh)}>
      <Banner kind="error" message={loadError} />
      <View style={styles.statsRow}>
        <View style={styles.statCard} accessible accessibilityLabel={`${organizations.length} organizations`}>
          <Text style={styles.statNumber}>{organizations.length}</Text>
          <Text style={styles.statLabel}>Organizations</Text>
        </View>
        <View style={styles.statCard} accessible accessibilityLabel={`${users.length} users`}>
          <Text style={styles.statNumber}>{users.length}</Text>
          <Text style={styles.statLabel}>Users</Text>
        </View>
      </View>
      <Button
        label={loadError ? 'Retry' : 'Refresh'}
        variant="secondary"
        onPress={onRefresh}
        loading={loading}
        loadingLabel="Refreshing"
        accessibilityHint="Reloads organizations and users"
      />
    </ScrollView>
  );
}

function ListTab({ title, data, loading, onRefresh, renderItem, emptyText }) {
  return (
    <FlatList
      data={data}
      keyExtractor={(item) => String(item.id)}
      renderItem={renderItem}
      contentContainerStyle={styles.tabContent}
      refreshControl={refreshControl(loading, onRefresh)}
      keyboardShouldPersistTaps="handled"
      ListHeaderComponent={
        <Text style={styles.sectionTitle} accessibilityRole="header">
          {title} ({data.length})
        </Text>
      }
      ListEmptyComponent={<Text style={styles.empty}>{emptyText}</Text>}
    />
  );
}

export function OrganizationsTab({ organizations, loading, onRefresh, onEdit, onDelete }) {
  return (
    <ListTab
      title="Organizations"
      data={organizations}
      loading={loading}
      onRefresh={onRefresh}
      emptyText="No organizations yet. Use the Create Org tab to add one."
      renderItem={({ item: org }) => (
        <View style={styles.card}>
          <View style={styles.cardRow}>
            <Text style={styles.cardTitle}>{org.name}</Text>
            <Text style={styles.badge}>{org.connector_type}</Text>
          </View>
          {org.industry ? <Text style={styles.cardSub}>{org.industry}</Text> : null}
          <View style={styles.cardActions}>
            <Button
              label="Edit"
              accessibilityLabel={`Edit ${org.name}`}
              variant="secondary"
              style={styles.cardBtn}
              onPress={() => onEdit(org)}
            />
            <Button
              label="Delete"
              accessibilityLabel={`Delete ${org.name}`}
              accessibilityHint="Asks for confirmation first"
              variant="danger"
              style={styles.cardBtn}
              onPress={() => onDelete(org)}
            />
          </View>
        </View>
      )}
    />
  );
}

export function UsersTab({ users, organizations, loading, onRefresh, onEdit, onResetPassword, onDelete }) {
  const orgName = (orgId) => organizations.find((o) => o.id === orgId)?.name || '—';
  return (
    <ListTab
      title="Users"
      data={users}
      loading={loading}
      onRefresh={onRefresh}
      emptyText="No users yet. Use the Create User tab to add one."
      renderItem={({ item: u }) => (
        <View style={styles.card}>
          <View style={styles.cardRow}>
            <Text style={styles.cardTitle} numberOfLines={1}>{u.email}</Text>
            <Text style={styles.badge}>{u.role}</Text>
          </View>
          <Text style={styles.cardSub}>Org: {orgName(u.org_id)}</Text>
          <View style={styles.cardActions}>
            <Button label="Edit" accessibilityLabel={`Edit ${u.email}`} variant="secondary" style={styles.cardBtn} onPress={() => onEdit(u)} />
            <Button
              label="Reset PW"
              accessibilityLabel={`Reset password for ${u.email}`}
              variant="secondary"
              style={styles.cardBtn}
              onPress={() => onResetPassword(u)}
            />
            <Button
              label="Delete"
              accessibilityLabel={`Delete ${u.email}`}
              accessibilityHint="Asks for confirmation first"
              variant="danger"
              style={styles.cardBtn}
              onPress={() => onDelete(u)}
            />
          </View>
        </View>
      )}
    />
  );
}
