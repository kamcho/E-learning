import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from subjects.curriculum_import import (
    CurriculumImportError,
    create_curriculum,
    parse_curriculum_text,
)

from subjects.forms import StrandForm, SubStrandForm
from subjects.models import Discipline, GradeLevel, Subject


class StrandFormTests(TestCase):
    def setUp(self):
        grade = GradeLevel.objects.create(
            name='Grade 1',
            slug='grade-1',
            level='Lower Primary',
        )
        discipline = Discipline.objects.create(
            name='Religious Education',
            slug='religious-education',
        )
        self.subject = Subject.objects.create(
            name='Religious Education Grade 1',
            slug='religious-education-grade-1',
            grade_level=grade,
            discipline=discipline,
        )

    def test_blank_slug_is_generated_from_strand_and_subject_names(self):
        form = StrandForm(data={
            'name': 'Creation',
            'order': 1,
            'subject': self.subject.pk,
        })

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data['slug'],
            'creation-religious-education-grade-1',
        )

    def test_strand_and_substrand_slug_inputs_use_the_standard_form_style(self):
        for form_class in (StrandForm, SubStrandForm):
            with self.subTest(form=form_class.__name__):
                widget = form_class().fields['slug'].widget
                self.assertEqual(widget.attrs.get('class'), 'form-input')
                self.assertEqual(
                    widget.attrs.get('placeholder'),
                    'Leave blank to auto-generate',
                )


class CurriculumImportTests(TestCase):
    def setUp(self):
        grade = GradeLevel.objects.create(
            name='Grade 1',
            slug='grade-1',
            level='Lower Primary',
        )
        discipline = Discipline.objects.create(
            name='Religious Education',
            slug='religious-education',
        )
        self.subject = Subject.objects.create(
            name='Religious Education Grade 1',
            slug='religious-education-grade-1',
            grade_level=grade,
            discipline=discipline,
        )

    def test_parse_curriculum_assigns_numbering_from_table_structure(self):
        client = Mock()
        client.chat.return_value = json.dumps([
            {
                'name': '1.0 Creation',
                'sub_strands': ['1.1 Self Awareness', '1.2 My Family'],
            },
            {
                'name': '2.0 The Holy Bible',
                'sub_strands': ['2.1 The Word of God'],
            },
        ])

        result = parse_curriculum_text(
            '| Strand | Sub-strand |\n| Creation | Self Awareness |',
            self.subject,
            client=client,
        )

        self.assertEqual(result[0]['name'], 'Creation')
        self.assertEqual(result[0]['order'], 1)
        self.assertEqual(result[0]['sub_strands'][0], {
            'name': 'Self Awareness',
            'order': 1,
        })
        self.assertIn('Religious Education Grade 1', client.chat.call_args.kwargs['user_prompt'])
        self.assertTrue(client.chat.call_args.kwargs['json_mode'])

    def test_invalid_ai_response_is_rejected(self):
        client = Mock()
        client.chat.return_value = 'not json'

        with self.assertRaises(CurriculumImportError):
            parse_curriculum_text('a curriculum table', self.subject, client=client)

    def test_parse_curriculum_accepts_json_object_with_strands(self):
        client = Mock()
        client.chat.return_value = json.dumps({
            'strands': [{
                'name': 'Creation',
                'sub_strands': ['Self Awareness'],
            }],
        })

        result = parse_curriculum_text('a curriculum table', self.subject, client=client)

        self.assertEqual(result[0]['name'], 'Creation')
        self.assertEqual(result[0]['sub_strands'][0]['name'], 'Self Awareness')

    def test_create_curriculum_creates_strands_and_sub_strands(self):
        curriculum = [{
            'name': 'Creation',
            'order': 1,
            'sub_strands': [{'name': 'Self Awareness', 'order': 1}],
        }]

        created = create_curriculum(self.subject, curriculum)

        self.assertEqual(created, (1, 1))
        self.assertEqual(self.subject.strands.get().slug, 'creation-religious-education-grade-1')
        self.assertEqual(
            self.subject.strands.get().sub_strands.get().name,
            'Self Awareness',
        )

    def test_create_curriculum_keeps_existing_entries_and_adds_missing_children(self):
        from subjects.models import Strand, SubStrand

        strand = Strand.objects.create(
            name='Creation',
            order=1,
            slug='creation-existing',
            subject=self.subject,
        )
        SubStrand.objects.create(
            name='Self Awareness',
            order=1,
            slug='self-awareness-existing',
            strand=strand,
        )
        curriculum = [{
            'name': 'Creation',
            'order': 1,
            'sub_strands': [
                {'name': 'Self Awareness', 'order': 1},
                {'name': 'My Family', 'order': 2},
            ],
        }]

        created = create_curriculum(self.subject, curriculum)

        self.assertEqual(created, (0, 1))
        self.assertEqual(self.subject.strands.count(), 1)
        self.assertEqual(strand.sub_strands.count(), 2)

    def test_subject_page_previews_before_importing_and_requires_admin(self):
        user_model = get_user_model()
        admin = user_model.objects.create_user(
            phone='0744444444',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )
        url = reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug})
        self.client.force_login(admin)
        with patch('subjects.curriculum_import.OpenAIClient') as openai_client:
            openai_client.return_value.chat.return_value = json.dumps([{
                'name': 'Creation',
                'sub_strands': ['Self Awareness'],
            }])
            response = self.client.post(url, {
                'action': 'parse_curriculum',
                'curriculum_text': 'Creation | Self Awareness',
            })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review parsed curriculum')
        self.assertContains(response, 'Confirm and create curriculum')
        self.assertEqual(self.subject.strands.count(), 0)

        response = self.client.post(url, {
            'action': 'import_curriculum',
            'preview_token': response.context['curriculum_preview_token'],
        })
        self.assertRedirects(response, url)
        self.assertEqual(self.subject.strands.count(), 1)

    def test_manual_strand_creation_still_works(self):
        admin = get_user_model().objects.create_user(
            phone='0744444446',
            password='1234',
            role=Role.ADMIN,
            first_name='Curriculum',
            last_name='Admin',
        )
        self.client.force_login(admin)
        url = reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug})

        response = self.client.post(url, {
            'action': 'create_strand',
            'name': 'Creation',
            'slug': '',
            'order': 1,
            'subject': self.subject.pk,
        })

        self.assertRedirects(response, url)
        self.assertEqual(
            self.subject.strands.get().slug,
            'creation-religious-education-grade-1',
        )

    def test_signed_preview_cannot_be_tampered_with(self):
        from django.core import signing
        from subjects.curriculum_import import PREVIEW_SALT, load_curriculum_preview

        token = signing.dumps([], salt=PREVIEW_SALT)
        with self.assertRaises(CurriculumImportError):
            load_curriculum_preview(token)

    def test_ai_preview_is_hidden_from_non_admins(self):
        user_model = get_user_model()
        teacher = user_model.objects.create_user(
            phone='0744444445',
            password='1234',
            role=Role.TEACHER,
            first_name='Teacher',
            last_name='User',
        )
        self.client.force_login(teacher)
        response = self.client.post(
            reverse('subjects:subject_detail', kwargs={'slug': self.subject.slug}),
            {'action': 'parse_curriculum', 'curriculum_text': 'curriculum'},
        )
        self.assertRedirects(response, reverse('core:landing'), fetch_redirect_response=False)
        self.assertEqual(self.subject.strands.count(), 0)
