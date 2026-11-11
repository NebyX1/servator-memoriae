"""Preserve independent OCR proposals and human review history."""
from alembic import op
import sqlalchemy as sa

revision = 'f42a9d3c8210'
down_revision = 'c9c5fea87e18'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('ocr_results',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('page_id', sa.String(36), sa.ForeignKey('pages.id'), nullable=False),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id'), nullable=False),
        sa.Column('engine', sa.String(32), nullable=False),
        sa.Column('model_version', sa.String(128), nullable=False),
        sa.Column('device', sa.String(16), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('text', sa.Text()), sa.Column('details', sa.JSON()),
        sa.Column('error', sa.Text()), sa.Column('created_at', sa.DateTime()),
        sa.UniqueConstraint('page_id', 'job_id', 'engine', name='uq_ocr_result_page_job_engine'))
    op.create_index('ix_ocr_results_page_id', 'ocr_results', ['page_id'])
    op.create_index('ix_ocr_results_job_id', 'ocr_results', ['job_id'])
    op.create_table('ocr_reviews',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('page_id', sa.String(36), sa.ForeignKey('pages.id'), nullable=False),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(32), nullable=False), sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
        sa.UniqueConstraint('page_id', 'version', name='uq_ocr_review_page_version'))
    op.create_index('ix_ocr_reviews_page_id', 'ocr_reviews', ['page_id'])


def downgrade():
    op.drop_index('ix_ocr_reviews_page_id', table_name='ocr_reviews')
    op.drop_table('ocr_reviews')
    op.drop_index('ix_ocr_results_job_id', table_name='ocr_results')
    op.drop_index('ix_ocr_results_page_id', table_name='ocr_results')
    op.drop_table('ocr_results')
